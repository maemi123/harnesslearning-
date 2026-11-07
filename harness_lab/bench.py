"""跑分器：拿一个 harness 去跑一批题，返回分数和失败明细。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import config, sandbox, tasks


@dataclass
class Problem:
    family: str
    question: str
    gold: str


@dataclass
class BenchResult:
    score: float                      # 平均分，0~1
    n: int
    details: list[dict]               # 每题明细
    usage: dict = field(default_factory=dict)   # 这一轮消耗的 token

    def failures(self, k: int) -> list[dict]:
        """挑几条最典型的失败给 proposer 看：先挑完全错的，再挑部分分的。"""
        bad = [d for d in self.details if d["score"] < 1.0]
        bad.sort(key=lambda d: d["score"])
        return bad[:k]

    def to_dict(self) -> dict:
        return {"score": round(self.score, 4), "n": self.n, "details": self.details}


def load_all() -> tuple[list[Problem], list[Problem]]:
    """返回 (开发集, 保留集)。同一族内两批题互不重叠。"""
    dev: list[Problem] = []
    ev: list[Problem] = []
    total = config.DEV_SIZE + config.EVAL_SIZE
    for i, fam in enumerate(config.FAMILIES):
        items = tasks.generate(fam, total, config.DATA_SEED + i * 1000)
        problems = [Problem(family=fam, question=t.question, gold=t.answer) for t in items]
        dev += problems[: config.DEV_SIZE]
        ev += problems[config.DEV_SIZE : total]
    return dev, ev


def run_benchmark(harness_path: Path, problems: list[Problem], tag: str = "") -> BenchResult:
    def work(p: Problem) -> dict:
        r = sandbox.run_one(harness_path, p.question)
        pred = r.get("answer", "")
        return {
            "family": p.family,
            "question": p.question,
            "gold": p.gold,
            "pred": pred,
            "score": tasks.score(p.family, pred, p.gold),
            "calls": r.get("calls", 0),
            "error": r.get("error"),
            "usage": r.get("usage") or {},
        }

    max_workers = max(1, min(config.WORKERS, len(problems)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        details = list(pool.map(work, problems))

    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for d in details:
        u = d.pop("usage", {}) or {}
        for k in usage:
            usage[k] += int(u.get(k, 0))

    score = sum(d["score"] for d in details) / max(1, len(details))
    if tag:
        full = sum(1 for d in details if d["score"] == 1.0)
        print(f"  [{tag}] {score:.3f}  ({full}/{len(details)} 满分, {usage['total_tokens']} tok)")
    return BenchResult(score=score, n=len(details), details=details, usage=usage)


def dump(result: BenchResult, path: Path) -> None:
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
