"""proposer：读执行报告 → 让模型改写 harness → 校验 → 落地。

注意这是"未训练的 base proposer"，也就是论文里 0.32 那条线。
我们不做 SFT、不做 RL，直接拿基座模型来改。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import config, llm, sandbox
from .bench import BenchResult

if config.OFFLINE:
    from ._offline import chat as _chat
else:
    _chat = llm.chat

SYSTEM = "你是一位专门优化 LLM 解题流程的工程师。你只输出代码，不解释。"

PROMPT_TMPL = """下面是一个 AI 解题程序（harness）的当前版本，以及它在一批题目上的真实运行记录。
你的任务：改写这段代码，让它在同类题目上答对更多。

【当前 harness】（当前平均分 {score:.3f}，满分 1.0）
```python
{source}
```

【它跑出来的失败记录】（从最严重的开始）
{failures}

【你只能调用这两个函数，没有别的东西】
- ask(prompt) -> str   把一段话发给解题模型，返回它的文字回答
- py(code) -> str      执行一段 Python 代码，**返回代码里 print 出来的内容**
                       如果代码出错，返回值以 "[ERR]" 开头

【最重要的三条，违反任何一条提案就作废】
1. 必须保留 `def run(question, ask, py):`，返回值就是最终答案字符串。
2. **必须保留兜底**：新逻辑失败时 `return ask(question)`。
   现在的分数是靠原有逻辑拿到的，新逻辑一旦出错又没兜底，分数会直接掉到 0。
3. 只输出一个完整、能编译的 Python 文件（用 ```python 包起来）。
   三引号要闭合、括号要配对——写一半断掉的文件会直接作废。

【沙箱限制】
- 不能用 import os / sys / subprocess / shutil
- 不能用 open() / eval() / exec() / __import__
- 可以用 re / math / json / datetime 这些纯计算库
- 不要自己搞动态执行，要跑代码就用 py()

【改动幅度】
只加必要的几行，不要重写整个文件。目标是让原来答对的题继续答对，再多答对一些。

【推荐结构】
def run(question, ask, py):
    # 只在你有把握的新场景里走新逻辑
    try:
        ...
        if 结果看起来靠谱:
            return 结果
    except Exception:
        pass
    # 其他情况原样退回，保证不比现在差
    return ask(question)

【已知有效的方向】
- 让模型把题目转成 Python 代码，交给 py() 算，而不是心算
- 要求模型只输出最终答案，减少废话
- 让模型自己验算一遍再回答

{extra}
请输出改进后的完整代码。"""


NO_HINT = ""


@dataclass
class Proposal:
    source: str | None
    reason: str = ""          # 失败原因，成功时为空


def _fmt_failures(result: BenchResult) -> str:
    out = []
    for i, d in enumerate(result.failures(config.PROPOSER_FEEDBACK_K), 1):
        out.append(f"{i}. 题目：{d['question']}")
        if d.get("error"):
            out.append(f"   运行报错：{str(d['error']).strip().splitlines()[-1][:200]}")
        else:
            out.append(f"   它答的：{d['pred'][:200]}")
        out.append(f"   正确答案：{d['gold'][:120]}")
        out.append("")
    return "\n".join(out) or "（这一轮全部答对，没有失败记录）"


_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)
_PATCH = re.compile(r"<<<<<<< SEARCH\s*\n(.*?)\n?=======\s*\n(.*?)\n?>>>>>>> REPLACE", re.S)


def _extract(text: str) -> str | None:
    """只认包含 def run( 的代码块。

    坑：模型经常先输出一段"我觉得可以这样"的片段，再给完整代码；
    也可能把代码写一半就断了。随便取最长块会拿到半截文件。
    """
    blocks = [b.strip() for b in _CODE_BLOCK.findall(text)]
    good = [b for b in blocks if "def run(" in b]
    if not good:
        return None
    return max(good, key=len).strip() + "\n"


def apply_patches(source: str, text: str) -> str | None:
    """SEARCH/REPLACE 格式的备选路径。"""
    patches = _PATCH.findall(text)
    if not patches:
        return None
    out = source
    for old, new in patches:
        if old not in out:
            return None
        out = out.replace(old, new, 1)
    return out


def propose(
    current: Path,
    result: BenchResult,
    round_idx: int,
    hint: str = "",
    max_tries: int = 2,
) -> Proposal:
    source = current.read_text(encoding="utf-8")
    prompt = PROMPT_TMPL.format(
        source=source,
        failures=_fmt_failures(result),
        score=result.score,
        extra=hint,
    )

    reason = ""
    for attempt in range(max_tries):
        reply = _chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            model=config.PROPOSER_MODEL,
            temperature=config.PROPOSER_TEMPERATURE,
            max_tokens=config.PROPOSER_MAX_TOKENS,
            enable_thinking=config.PROPOSER_THINKING,
        )

        candidate = _extract(reply) or apply_patches(source, reply)
        if candidate:
            problem = sandbox.check_source(candidate)
            if not problem:
                return Proposal(candidate)
            reason = problem
        else:
            reason = "输出里没有完整的代码块"

        # 带着上一次的错误再问一遍，命中率明显更高
        prompt += (
            f"\n\n【上一次你输出的代码有问题】{reason}\n"
            "请重新输出**完整**的 Python 文件，从第一行到最后一个字符都要写全，不要中途停。\n"
            "注意：不能使用 eval/exec/os/sys/open，需要算东西就直接调 py(代码字符串)。\n"
            "如果你之前写了 eval(...)，请改成：把表达式拼成 'print(表达式)' 然后交给 py()。\n"
        )

    return Proposal(None, reason)
