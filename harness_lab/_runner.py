"""子进程入口：加载 harness、注入 ask/py、跑一道题、把结果写成 JSON。

不要直接调这个文件，统一走 sandbox.run_one()。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from harness_lab import config  # noqa: E402

if config.OFFLINE:
    from harness_lab._offline import chat  # noqa: E402
    _usage_snapshot = lambda: {}  # noqa: E731
else:
    from harness_lab.llm import chat  # noqa: E402
    from harness_lab.llm import USAGE  # noqa: E402

    _usage_snapshot = USAGE.snapshot


_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def _tidy(code: str) -> str:
    """把模型爱加的 markdown 围栏去掉。这是执行环境该做的，不该让 harness 去猜。"""
    m = _FENCE.search(code)
    return (m.group(1) if m else code).strip()


def _exec_py(code: str) -> str:
    src = _tidy(str(code))
    if not src:
        return "[ERR] 空代码"

    # 先当语句执行，拿 print 出来的东西。
    # 注意顺序：不能先试 eval——在 Python3 里 print(x) 也是合法表达式，
    # eval 会把输出吞掉、返回 None。
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(src, "<snippet>", "exec"), {"__name__": "__sandbox__"})
    except Exception as e:
        return f"[ERR] {type(e).__name__}: {e}\n{buf.getvalue()[-500:]}"

    out = buf.getvalue()
    if out.strip():
        return out[: config.PY_MAX_OUTPUT]

    # 一行都没 print，可能是直接给了个表达式（"2924*14+879-38"），求值返回
    try:
        value = eval(compile(src, "<snippet>", "eval"), {"__name__": "__sandbox__"})
        return repr(value)
    except Exception:
        return "(无输出：需要结果请 print 出来)"


def main() -> None:
    harness_path, job_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    budget = int(job.get("budget", config.SOLVER_CALL_BUDGET))

    state = {"calls": 0}

    def ask(prompt: str) -> str:
        if state["calls"] >= budget:
            return "[ERR] 已达到本题的模型调用上限"
        state["calls"] += 1
        try:
            return chat(
                [{"role": "user", "content": str(prompt)}],
                model=config.SOLVER_MODEL,
                temperature=config.SOLVER_TEMPERATURE,
                max_tokens=config.SOLVER_MAX_TOKENS,
                enable_thinking=config.SOLVER_THINKING,
            )
        except Exception as e:  # 模型挂了不能让整题崩
            return f"[ERR] 模型调用失败：{e}"

    def py(code: str) -> str:
        return _exec_py(code)

    result = {"answer": "", "calls": 0, "error": None}
    try:
        spec = importlib.util.spec_from_file_location("harness_under_test", harness_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        if not hasattr(mod, "run"):
            raise AttributeError("harness 里没有定义 run(question, ask, py)")
        answer = mod.run(job["question"], ask, py)
        result["answer"] = "" if answer is None else str(answer)
    except Exception:
        result["error"] = traceback.format_exc(limit=3)[-800:]

    result["calls"] = state["calls"]
    result["usage"] = _usage_snapshot()
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
