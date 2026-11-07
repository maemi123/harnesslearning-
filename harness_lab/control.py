"""对照实验：手工写一个"正确改动"，看评分链路能不能认出来。

用途：把「闭环基础设施好不好」和「proposer 会不会写代码」两件事分开。
如果这个版本能拿高分，说明基础设施没问题，瓶颈在 proposer。

跑法：python -m harness_lab.control
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import bench, config

RE_EXPR = re.compile(r"计算：(.+?)\s*的值")

CONTROL = '''
import re

RE_EXPR = re.compile(r"计算：(.+?)\\s*的值")

def run(question, ask, py):
    # 算术题：从题面抠出表达式，交给 Python 算
    m = RE_EXPR.search(question)
    if m:
        expr = m.group(1).replace("×", "*").replace("÷", "/")
        out = py("print(" + expr + ")")
        if out and not out.startswith("[ERR]"):
            return out.strip()

    # 日期题：让模型写代码算，而不是心算
    if "天是几月几号" in question:
        code = ask("用 Python 计算下面这道日期题，只输出代码，不要解释：\\n" + question)
        out = py(code)
        if out and not out.startswith("[ERR]") and out.strip():
            return out.strip()

    # 方程题和其他情况：原样退回
    return ask(question)
'''


def main() -> None:
    dev, ev = bench.load_all()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "control.py"
        path.write_text(CONTROL, encoding="utf-8")

        by_fam: dict[str, list] = {}
        for p in dev:
            by_fam.setdefault(p.family, []).append(p)

        for fam, items in by_fam.items():
            res = bench.run_benchmark(path, items, f"control {fam}")
            errs = sum(1 for d in res.details if d["error"])
            print(f"     {fam}: {res.score:.2f}  错误 {errs}  {res.usage['total_tokens']} tok")


if __name__ == "__main__":
    main()
