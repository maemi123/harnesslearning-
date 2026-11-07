"""用"没见过的题型"考最终 harness：检验它是真学会了，还是只会背练过的那三种题面。

用法：
    python -m harness_lab.heldout_family
"""

from __future__ import annotations

import time

from . import bench, config, tasks

# 两个都没有参与改进的题型
CASES = [
    ("percent_discount", 777, "ref_discount.py", "打折计算（基线约 0.7）"),
    ("base_conversion", 888, "ref_base.py", "进制转换（基线应接近 0）"),
]

VERSIONS = [
    ("第 0 层 seed", config.SEED_PATH),
    ("跑完 5 轮", config.HARNESS_PATH),
]


def main() -> None:
    for fam, seed, ref_name, desc in CASES:
        items = tasks.generate(fam, 20, seed=seed)
        problems = [bench.Problem(family=fam, question=t.question, gold=t.answer) for t in items]
        print(f"\n===== {desc}｜题型 {fam}｜20 道 =====")
        print("例题：", problems[0].question, "| 答案", problems[0].gold)

        for name, path in VERSIONS:
            t = time.time()
            r = bench.run_benchmark(path, problems, "")
            print(f"  {name:12s} {r.score:.3f}   ({time.time() - t:.0f}s, {r.usage['total_tokens']} tok)")

        ref = config.ROOT / "_tmp" / ref_name
        if ref.exists():
            r = bench.run_benchmark(ref, problems, "")
            print(f"  {'手写解析器':12s} {r.score:.3f}   （证明题可解、判分没错）")


if __name__ == "__main__":
    main()
