"""按论文的协议测「全新题型」：给该题型的开发题错题报告 → 改一次 → 考同类新题。

和 heldout_family.py 的区别（这是两个不同的问题）：

  heldout_family.py
      不给任何报告，直接拿在别的题型上练好的 harness 去考
      → 测的是「harness 跨题型通不通用」

  本脚本
      给它该题型的 20 道开发题（带答案），让它看错在哪，允许针对这个题型改一次
      → 测的是「proposer 面对一个新题型，能不能改对」（= 论文 unseen family 的协议）

用法：
    python -m harness_lab.newfamily_probe
"""

from __future__ import annotations

import json
import time

from . import bench, config, proposer, tasks

# (题型, 随机种子, 中文名, 备注)
CASES = [
    ("percent_discount", 777, "打折计算", "基线约 0.75"),
    ("base_conversion", 888, "进制转换", "基线接近 0"),
]

DEV_N = 20       # 给它看错题的练习题
TEST_N = 20      # 改完之后考的同类新题
OUT = config.ROOT / "runs" / "newfamily"


def _expand(fam: str, items) -> list[bench.Problem]:
    return [bench.Problem(family=fam, question=t.question, gold=t.answer) for t in items]


def probe(fam: str, seed: int, name: str, note: str) -> dict:
    items = tasks.generate(fam, DEV_N + TEST_N, seed=seed)
    dev = _expand(fam, items[:DEV_N])
    test = _expand(fam, items[DEV_N:])

    print(f"\n===== {name}（{fam}）｜{note} =====")
    print(f"  考卷例题：{test[0].question}")
    print(f"  正确答案：{test[0].gold}")

    # 1) 改之前，先考一次（这就是基线）
    base = bench.run_benchmark(config.SEED_PATH, test, "改之前 → 考卷")

    # 2) 用开发题跑一遍，产出错题报告（论文的 Q_fb）
    dev_res = bench.run_benchmark(config.SEED_PATH, dev, "第0层 → 练习题")

    # 3) 让 proposer 针对这个题型改一次
    t0 = time.time()
    p = proposer.propose(config.SEED_PATH, dev_res, 1)
    print(f"  提案耗时 {time.time() - t0:.0f}s｜可用={p.source is not None}｜{p.reason}")

    row = {
        "family": fam,
        "name": name,
        "before": round(base.score, 4),
        "after": None,
        "accepted": False,
        "reason": p.reason,
        "tokens": base.usage.get("total_tokens", 0) + dev_res.usage.get("total_tokens", 0),
    }

    if p.source is None:
        print("  提案不可用，直接记 0 收益")
        return row

    OUT.mkdir(parents=True, exist_ok=True)
    cand = OUT / f"{fam}_candidate.py"
    cand.write_text(p.source, encoding="utf-8")
    print(f"  候选代码已存：{cand.relative_to(config.ROOT)}（{len(p.source.splitlines())} 行）")

    # 4) 改完之后，考同一批新题
    after = bench.run_benchmark(cand, test, "改之后 → 考卷")
    row["after"] = round(after.score, 4)
    row["delta"] = round(after.score - base.score, 4)
    row["tokens"] += after.usage.get("total_tokens", 0)

    # 5) 顺便看它在练习题上是不是真变好了（防止只对考卷有效）
    dev_after = bench.run_benchmark(cand, dev, "改之后 → 练习题")
    row["dev_before"] = round(dev_res.score, 4)
    row["dev_after"] = round(dev_after.score, 4)
    row["tokens"] += dev_after.usage.get("total_tokens", 0)

    return row


def main() -> None:
    print(f"proposer = {config.PROPOSER_MODEL}｜solver = {config.SOLVER_MODEL}")
    print(f"每种题型：{DEV_N} 道练习题（给报告）+ {TEST_N} 道考卷（同类新题）")

    rows = []
    for fam, seed, name, note in CASES:
        rows.append(probe(fam, seed, name, note))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n\n================ 汇总 ================")
    print(f"{'题型':10s} {'改之前':>7s} {'改之后':>7s} {'变化':>7s} {'练习题':>13s}")
    for r in rows:
        after = f"{r['after']:.3f}" if r["after"] is not None else "  —  "
        delta = f"{r.get('delta', 0):+.3f}" if r["after"] is not None else "  —  "
        dev = (f"{r.get('dev_before', 0):.2f} → {r.get('dev_after', 0):.2f}"
               if "dev_after" in r else "—")
        print(f"{r['name']:10s} {r['before']:7.3f} {after:>7s} {delta:>7s}   {dev}")
    print(f"\n结果已存：{OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
