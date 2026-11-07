"""把一次实验的产物整理成人能读的报告：python -m harness_lab.report [run目录]"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

from . import config


def _latest_run() -> Path:
    runs = sorted(p for p in config.RUNS_DIR.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit("还没有实验记录")
    return runs[-1]


def build(run_dir: Path) -> str:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    lines: list[str] = [
        f"# 实验报告 · {run_dir.name}",
        "",
        f"- solver：`{summary['solver']}`",
        f"- proposer：`{summary['proposer']}`",
        f"- 题族：{', '.join(summary['families'])}",
        f"- 轮数：{summary['rounds']}（接受 {summary['accepted_rounds']} 次）",
        f"- 耗时：{summary['elapsed_sec'] / 60:.1f} 分钟",
        f"- token：{summary['usage']['total_tokens']:,}（{summary['usage']['calls']} 次调用）",
        "",
        "## 分数",
        "",
        "| 阶段 | 分数 |",
        "|---|---|",
        f"| 第 0 层（seed） | {summary['seed_dev_score']:.3f} |",
        f"| 开发集最好 | {summary['best_dev_score']:.3f} |",
        f"| **保留集（最终考核）** | **{summary['heldout_score']:.3f}** |",
        "",
        "## 每轮发生了什么",
        "",
        "| 轮 | 开发集分数 | 结果 | 说明 |",
        "|---|---|---|---|",
    ]
    for h in summary["history"]:
        mark = "✅ 接受" if h["accepted"] else "❌ 丢弃"
        lines.append(f"| {h['round']} | {h['score']:.3f} | {mark} | {h['note']} |")

    # 逐轮 diff
    snaps = sorted(run_dir.glob("round_*_harness.py"))
    if len(snaps) >= 1:
        lines += ["", "## harness 是怎么一步步变的", ""]
        prev = (config.SEED_PATH).read_text(encoding="utf-8")
        for snap in snaps:
            cur = snap.read_text(encoding="utf-8")
            if cur.strip() == prev.strip():
                continue
            diff = list(
                difflib.unified_diff(
                    prev.splitlines(), cur.splitlines(),
                    fromfile="上一版", tofile=snap.stem, lineterm="", n=2,
                )
            )
            body = "\n".join(diff[2:])  # 去掉 --- / +++ 头
            lines += [f"### {snap.stem}", "", "```diff", body[:4000], "```", ""]
            prev = cur

    # 失败样例
    ev = run_dir / "final_eval.json"
    if ev.exists():
        data = json.loads(ev.read_text(encoding="utf-8"))
        bad = [d for d in data["details"] if d["score"] < 1.0][:8]
        lines += ["", "## 保留集上还错在哪", ""]
        if not bad:
            lines.append("全对。")
        for d in bad:
            tail = (d["pred"] or "").strip().replace("\n", " ")[-80:]
            lines.append(f"- `{d['family']}`｜{d['question'][:60]} → 答 `{tail}`，正确 `{d['gold']}`")

    return "\n".join(lines) + "\n"


def main() -> None:
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_run()
    text = build(run_dir)
    out = run_dir / "report.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
