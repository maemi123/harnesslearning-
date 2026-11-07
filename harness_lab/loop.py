"""主循环：跑分 → 出报告 → 改 harness → 再跑分。

用法：
    set HL_API_KEY=sk-xxx
    python -m harness_lab.loop            # 完整 8 轮
    python -m harness_lab.loop --rounds 3 # 先跑 3 轮试试水
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import bench, config, llm, proposer, sandbox


def _snapshot(src: Path, dst: Path) -> None:
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _log(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=config.MAX_ROUNDS)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    if not config.OFFLINE and not config.API_KEY:
        print("还没设置 API key。先做这两步：")
        print("  1. 到 https://cloud.siliconflow.cn 注册，创建 API Key（Qwen3.5-4B 免费）")
        print("  2. Windows:  set HL_API_KEY=sk-xxx")
        print("     然后重跑：  python -m harness_lab.loop")
        print("\n只想验证管路通不通：set HL_OFFLINE=1 再跑一次（分数无意义）")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{args.tag}" if args.tag else "")
    run_dir = config.RUNS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "log.jsonl"

    t0 = time.time()
    print(f"== 实验目录 {run_dir.name} ==")
    print(f"   solver   : {config.SOLVER_MODEL}")
    print(f"   proposer : {config.PROPOSER_MODEL}")
    print(f"   题族     : {', '.join(config.FAMILIES)}")
    print(f"   开发集 {config.DEV_SIZE} 题/族 · 保留集 {config.EVAL_SIZE} 题/族")

    # 每次实验都从第 0 层干净开始
    shutil.copyfile(config.SEED_PATH, config.HARNESS_PATH)

    dev, ev = bench.load_all()
    print(f"   共 {len(dev)} 道开发题、{len(ev)} 道保留题\n")

    # 冒烟集：每族取 2 题，覆盖所有题型，避免"只适配了一个族"被误判
    smoke_set, seen = [], {}
    for p in dev:
        if seen.get(p.family, 0) < 2:
            smoke_set.append(p)
            seen[p.family] = seen.get(p.family, 0) + 1

    total_usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def acc(u: dict | None) -> None:
        for k in total_usage:
            total_usage[k] += int((u or {}).get(k, 0))

    # ---- 第 0 轮：基线 ----
    print("[round 0] 跑基线（未经任何改动）")
    base = bench.run_benchmark(config.HARNESS_PATH, dev, "seed")
    acc(base.usage)
    bench.dump(base, run_dir / "round_00_score.json")
    _snapshot(config.HARNESS_PATH, run_dir / "round_00_harness.py")
    _log(log_path, {
        "round": 0, "event": "baseline", "score": base.score,
        "accepted": True, "reason": "", "usage": llm.USAGE.snapshot(),
    })

    seed_score = base.score
    best_score = base.score
    history = [{"round": 0, "score": base.score, "accepted": True, "note": "seed"}]
    accepted = 0

    # ---- 迭代 ----
    last_hint = ""
    for r in range(1, args.rounds + 1):
        print(f"[round {r}] 让 proposer 读报告并改写")
        p_before = llm.USAGE.snapshot()
        try:
            prop = proposer.propose(config.HARNESS_PATH, base, r, hint=last_hint)
        except llm.LLMError as e:
            print(f"   ✗ 调用失败：{e}")
            history.append({"round": r, "score": best_score, "accepted": False, "note": str(e)})
            break
        p_after = llm.USAGE.snapshot()
        acc({k: p_after[k] - p_before.get(k, 0) for k in p_after})

        if prop.source is None:
            print(f"   ✗ 提案被拒：{prop.reason}")
            last_hint = (
                f"【上一轮你写的代码被拒了】原因：{prop.reason}\n"
                "这次务必避开这个问题：代码要完整、要能编译、只用 ask() 和 py()。\n"
            )
            history.append({"round": r, "score": best_score, "accepted": False, "note": prop.reason})
            _log(log_path, {
                "round": r, "event": "proposal_rejected", "score": best_score,
                "accepted": False, "reason": prop.reason, "usage": llm.USAGE.snapshot(),
            })
            continue

        cand_path = run_dir / f"round_{r:02d}_candidate.py"
        cand_path.write_text(prop.source, encoding="utf-8")

        # 先在一小组题上试跑，一跑就崩、或者一题都不对的，直接扔掉省时间
        smoke = bench.run_benchmark(cand_path, smoke_set, f"round {r} smoke")
        acc(smoke.usage)
        crashed = sum(1 for d in smoke.details if d["error"])
        if crashed == len(smoke.details) or smoke.score == 0.0:
            reason = (
                f"候选版本在冒烟测试里全部崩溃：{smoke.details[0]['error']}"
                if crashed == len(smoke.details)
                else f"候选版本在 {len(smoke.details)} 道题上一题都没答对"
            )
            print(f"   ✗ 提案被拒：{reason}")
            last_hint = (
                f"【上一轮你写的代码跑出来一题都没答对】{reason}\n"
                "请检查：ask() 必须传字符串；py() 返回的是 print 出来的内容；"
                "判断结果是否可用时，不要写死格式，用 strip() 后再判断。\n"
            )
            history.append({"round": r, "score": best_score, "accepted": False, "note": "跑不起来"})
            _log(log_path, {
                "round": r, "event": "proposal_crashed", "score": best_score,
                "accepted": False, "reason": reason, "usage": llm.USAGE.snapshot(),
            })
            continue

        full = bench.run_benchmark(cand_path, dev, f"round {r} dev")
        acc(full.usage)

        if full.score > best_score + 1e-9:
            shutil.copyfile(cand_path, config.HARNESS_PATH)
            _snapshot(config.HARNESS_PATH, run_dir / f"round_{r:02d}_harness.py")
            bench.dump(full, run_dir / f"round_{r:02d}_score.json")
            accepted += 1
            note = f"接受 +{full.score - best_score:.3f}"
            print(f"   ✓ {note}")
            best_score = full.score
            base = full
            history.append({"round": r, "score": full.score, "accepted": True, "note": note})
            _log(log_path, {
                "round": r, "event": "accepted", "score": full.score,
                "accepted": True, "reason": note, "usage": llm.USAGE.snapshot(),
            })
        else:
            note = f"没涨（{full.score:.3f} ≤ {best_score:.3f}），丢弃"
            print(f"   ✗ {note}")
            last_hint = (
                f"【上一轮你的改动让分数从 {best_score:.3f} 掉到 {full.score:.3f}】\n"
                "这说明新逻辑把原本能答对的题弄错了。必须加兜底：新逻辑失败时 return ask(question)。\n"
                "改动幅度再小一点，只针对失败记录里那几道题。\n"
            )
            history.append({"round": r, "score": best_score, "accepted": False, "note": note})
            _log(log_path, {
                "round": r, "event": "rejected", "score": full.score,
                "accepted": False, "reason": note, "usage": llm.USAGE.snapshot(),
            })

    # ---- 最终考核：保留集，从没给 proposer 看过 ----
    print("\n[eval] 用保留集算最终成绩（proposer 全程没见过这些题）")
    final = bench.run_benchmark(config.HARNESS_PATH, ev, "held-out")
    acc(final.usage)
    bench.dump(final, run_dir / "final_eval.json")

    usage = total_usage
    elapsed = time.time() - t0
    summary = {
        "run": run_dir.name,
        "solver": config.SOLVER_MODEL,
        "proposer": config.PROPOSER_MODEL,
        "families": config.FAMILIES,
        "seed_dev_score": round(seed_score, 4),
        "best_dev_score": round(best_score, 4),
        "heldout_score": round(final.score, 4),
        "accepted_rounds": accepted,
        "rounds": args.rounds,
        "usage": usage,
        "elapsed_sec": round(elapsed, 1),
        "history": history,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n== 结果 ==")
    print(f"   开发集：{seed_score:.3f} → {best_score:.3f}")
    print(f"   保留集：{final.score:.3f}")
    print(f"   接受 {accepted}/{args.rounds} 次改动")
    print(f"   token：{usage['total_tokens']:,}（{usage['calls']} 次调用）")
    print(f"   耗时：{elapsed / 60:.1f} 分钟")
    print(f"   产物：{run_dir}")


if __name__ == "__main__":
    main()
