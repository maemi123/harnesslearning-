"""独立验证三个难题族：题目可解、答案唯一、判分正确。

原则：验证逻辑不复用 tasks.py 里的实现，免得"自己验自己"。
"""

from __future__ import annotations

import random
import re
from collections import deque

from . import tasks

KNOWN_QUEENS = {10: 724, 11: 2680, 12: 14200, 13: 73712}


def check_maze() -> None:
    items = tasks.generate("maze_grid", 6, 7)
    print(f"\n=== maze_grid：{len(items)} 道 ===")
    for t in items:
        lines = t.question.splitlines()
        body = [l for l in lines if set(l) <= set("#.SE") and l]
        start = next((x, y) for y, row in enumerate(body) for x, ch in enumerate(row) if ch == "S")
        goal = next((x, y) for y, row in enumerate(body) for x, ch in enumerate(row) if ch == "E")
        # 独立 BFS
        dist = {start: 0}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= ny < len(body) and 0 <= nx < len(body[0]) \
                        and body[ny][nx] != "#" and (nx, ny) not in dist:
                    dist[(nx, ny)] = dist[(x, y)] + 1
                    q.append((nx, ny))
        want = int(t.answer)
        ok = dist.get(goal) == want
        print(f"  {'OK ' if ok else 'BAD'} {len(body[0])}x{len(body)} 步数={want}")
        if not ok:
            print(t.question)
            print("独立 BFS 得到：", dist.get(goal))


def check_sudoku() -> None:
    items = tasks.generate("sudoku_4x4", 4, 11)
    print(f"\n=== sudoku_4x4：{len(items)} 道 ===")
    for t in items:
        lines = [l for l in t.question.splitlines() if re.fullmatch(r"[0-4 ]+", l.strip()) and l.strip()]
        grid = [[int(v) for v in l.split()] for l in lines]
        sol = [int(c) for c in t.answer]
        # 检查终盘合法
        ok_rows = all(sorted(sol[r * 4:(r + 1) * 4]) == [1, 2, 3, 4] for r in range(4))
        ok_cols = all(sorted(sol[c::4]) == [1, 2, 3, 4] for c in range(4))
        ok_box = True
        for br in (0, 2):
            for bc in (0, 2):
                box = [sol[(br + i) * 4 + bc + j] for i in range(2) for j in range(2)]
                ok_box &= sorted(box) == [1, 2, 3, 4]
        # 检查终盘和题面不冲突
        ok_given = all(grid[r][c] in (0, sol[r * 4 + c]) for r in range(4) for c in range(4))
        holes = sum(1 for r in range(4) for c in range(4) if grid[r][c] == 0)
        good = ok_rows and ok_cols and ok_box and ok_given
        print(f"  {'OK ' if good else 'BAD'} 空格={holes} 答案={t.answer}")
        if not good:
            print(t.question, ok_rows, ok_cols, ok_box, ok_given)


def check_queens() -> None:
    items = tasks.generate("n_queens", 8, 3)
    print(f"\n=== n_queens：{len(items)} 道 ===")
    for t in items:
        m = re.search(r"(\d+)×", t.question)
        n = int(m.group(1))
        ok = int(t.answer) == KNOWN_QUEENS[n]
        print(f"  {'OK ' if ok else 'BAD'} n={n} 方案数={t.answer}（已知 {KNOWN_QUEENS[n]}）")


def check_scorers() -> None:
    print("\n=== 判分函数 ===")
    cases = [
        ("maze_grid", "最少需要 27 步。", "27", 1.0),
        ("maze_grid", "27", "27", 1.0),
        ("maze_grid", "答案是 31 步", "27", 0.0),
        ("sudoku_4x4", "1 2 3 4 / 3 4 1 2 / 2 1 4 3 / 4 3 2 1", "1234341221434321", 1.0),
        ("sudoku_4x4", "第一行 1 2 3 4，最后答案是 1234341221434321", "1234341221434321", 1.0),
        ("sudoku_4x4", "1234", "1234341221434321", 0.0),
        ("n_queens", "一共有 2680 种摆法。", "2680", 1.0),
        ("n_queens", "11 个皇后有 2680 种", "2680", 1.0),
    ]
    for fam, pred, gold, want in cases:
        got = tasks.score(fam, pred, gold)
        ok = abs(got - want) < 1e-9
        print(f"  {'OK ' if ok else 'BAD'} {fam}: {pred[:28]!r} -> {got}")


if __name__ == "__main__":
    random.seed(0)
    check_maze()
    check_sudoku()
    check_queens()
    check_scorers()
    print("\n完成。")
