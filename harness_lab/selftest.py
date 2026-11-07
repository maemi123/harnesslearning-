"""自检：不调真模型，验证「沙箱能执行代码 → 评分能认对 → 改好的 harness 分数真的会涨」。

跑法：python -m harness_lab.selftest
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import bench, config, sandbox

GOOD_HARNESS = '''
import re

def run(question, ask, py):
    # 只用工具、不靠模型：把算式从题面里抠出来，交给 Python 算
    m = re.search(r"计算：(.+?)\\s*的值", question)
    if m:
        expr = m.group(1).replace("×", "*").replace("÷", "/").replace("−", "-")
        return py("print(" + expr + ")")
    return ask(question)
'''

BAD_HARNESS = '''
import os

def run(question, ask, py):
    return ask(question)
'''


def main() -> None:
    dev, ev = bench.load_all()
    print(f"开发集 {len(dev)} 题 / 保留集 {len(ev)} 题")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        seed = td / "seed.py"
        shutil.copyfile(config.SEED_PATH, seed)
        print("\n[1] 第 0 层 harness（纯靠模型，离线假模型只会答 0）")
        r0 = bench.run_benchmark(seed, dev, "seed")

        good = td / "good.py"
        good.write_text(GOOD_HARNESS, encoding="utf-8")
        print("\n[2] 手工改进版（用 py 算，不靠模型）")
        r1 = bench.run_benchmark(good, dev, "good")

        print(f"\n    分数变化：{r0.score:.3f} → {r1.score:.3f}")
        arith = [d for d in r1.details if d["family"] == "basic_arithmetic"]
        hit = sum(1 for d in arith if d["score"] == 1.0)
        print(f"    算术族：{hit}/{len(arith)} 答对")
        if arith and arith[0]["score"] == 0.0:
            print(f"    样例：Q={arith[0]['question']}  预测={arith[0]['pred']!r}")

        print("\n[3] 违规代码应该被挡下")
        bad = sandbox.check_source(BAD_HARNESS)
        print(f"    拦截结果：{bad}")
        ok = sandbox.check_source(GOOD_HARNESS)
        print(f"    合规代码检查：{'通过' if ok is None else ok}")

    assert r1.score > r0.score, "改进版没有更高分，题族或评分器有问题"
    assert bad and "禁止" in bad, "黑名单没生效"
    print("\n自检通过：链路是通的，改好 harness 分数确实会涨。")


if __name__ == "__main__":
    main()
