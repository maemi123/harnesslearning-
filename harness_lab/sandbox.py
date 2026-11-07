"""沙箱执行层：把任意 harness 代码丢进独立子进程跑，父进程只管超时和收尸。

不是真正的安全沙箱（Windows 上没有便宜的方案），但挡住了三类最常见的事故：
  - 死循环        → 父进程 timeout 杀掉
  - 写坏文件      → 黑名单挡住 os / subprocess / open(...,'w')
  - 抛异常        → 记零分，不影响其他题
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

# 静态黑名单：模型写的 harness 里出现这些就拒收
BANNED_TOKENS = [
    "import os",
    "import sys",
    "import subprocess",
    "import shutil",
    "import socket",
    "import ctypes",
    "__import__",
    "eval(",
    "exec(",
    "os.system",
    "os.remove",
    "os.rmdir",
    "shutil.",
    "open(",
    "pathlib",
]

RUNNER = Path(__file__).resolve().parent / "_runner.py"


class SandboxError(RuntimeError):
    pass


def check_source(source: str) -> str | None:
    """返回 None 表示通过，否则返回拒绝原因。"""
    lines = source.splitlines()
    if len(lines) > config.HARNESS_MAX_LINES:
        return f"代码超过 {config.HARNESS_MAX_LINES} 行（{len(lines)} 行）"
    if "def run(" not in source:
        return "没有定义 run(question, ask, py)"
    for tok in BANNED_TOKENS:
        if tok in source:
            return f"使用了被禁止的写法：{tok}"
    try:
        compile(source, "<harness>", "exec")
    except SyntaxError as e:
        return f"语法错误：{e.msg}（第 {e.lineno} 行）"
    return None


def run_one(harness_path: Path, question: str, budget: int | None = None) -> dict:
    """在一道题上跑一次 harness。返回 {answer, calls, error}。"""
    budget = budget or config.SOLVER_CALL_BUDGET
    with tempfile.TemporaryDirectory(prefix="hl_") as td:
        job = Path(td) / "job.json"
        out = Path(td) / "out.json"
        job.write_text(
            json.dumps({"question": question, "budget": budget}, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            subprocess.run(
                [sys.executable, str(RUNNER), str(harness_path), str(job), str(out)],
                cwd=str(config.ROOT.parent),
                timeout=config.RUN_TIMEOUT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except subprocess.TimeoutExpired:
            return {"answer": "", "calls": 0, "error": f"超时 {config.RUN_TIMEOUT}s"}

        if not out.exists():
            return {"answer": "", "calls": 0, "error": "子进程没有产出结果（多半是崩了）"}
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"answer": "", "calls": 0, "error": "结果不是合法 JSON"}
