"""汇总 hard_* 实验：每个 proposer 在难题族上的开发集/保留集成绩。

用法：python -m harness_lab.summarize_hard
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config


def main() -> None:
    rows = []
    for d in sorted(config.RUNS_DIR.glob("*_hard_*")):
        f = d / "summary.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        rejects = [h for h in s["history"][1:] if not h["accepted"]]
        syntax = sum(1 for h in rejects if "语法错误" in h.get("note", ""))
        rows.append({
            "proposer": s["proposer"].split("/")[-1],
            "seed": s["seed_dev_score"],
            "dev": s["best_dev_score"],
            "held": s["heldout_score"],
            "acc": f'{s["accepted_rounds"]}/{s["rounds"]}',
            "syntax": syntax,
            "tok": s["usage"]["total_tokens"],
            "min": round(s["elapsed_sec"] / 60, 1),
            "run": d.name,
        })

    if not rows:
        print("没有 hard_* 实验")
        return

    hdr = f"{'proposer':26s} {'基线':>6s} {'开发集':>7s} {'保留集':>7s} {'接受':>6s} {'语法错':>6s} {'token':>8s} {'分钟':>6s}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['proposer']:26s} {r['seed']:6.3f} {r['dev']:7.3f} {r['held']:7.3f} "
            f"{r['acc']:>6s} {r['syntax']:6d} {r['tok']:8,d} {r['min']:6.1f}"
        )


if __name__ == "__main__":
    main()
