"""题族：自己造的，但接口和 reasoning-gym 一样（question / answer / score）。

为什么不用 reasoning-gym：它依赖 pycosat，Windows + Python 3.13 没有预编译包，
本地编译失败。自建题库反而更可控，而且后面换成 GIS 题只需要改这个文件。

设计原则（很关键）：
  - 题目只会"直接问"，不给任何格式提示 —— 格式规范该由 harness 自己学会
  - 每题都有唯一可验证的正确答案
  - 数字都大到心算必错，给"引入代码执行"留出改进空间
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass


@dataclass
class Task:
    family: str
    question: str
    answer: str


# ---------------- 答案抽取与判分 ----------------

_NUM = re.compile(r"-?\d[\d,]*\.?\d*")
_DATE_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _last_number(text: str) -> float | None:
    """取回答里最后一个数字。模型爱写'所以答案是 12345'，取最后一个最稳。"""
    if not text:
        return None
    hits = _NUM.findall(text.replace("，", ","))
    if not hits:
        return None
    try:
        return float(hits[-1].replace(",", ""))
    except ValueError:
        return None


def _score_number(pred: str, gold: str) -> float:
    got = _last_number(pred)
    if got is None:
        return 0.0
    want = float(gold)
    if abs(want) > 1e-9:
        return 1.0 if abs(got - want) <= abs(want) * 1e-6 else 0.0
    return 1.0 if abs(got) < 1e-6 else 0.0


def _norm_date(text: str) -> str | None:
    """取回答里**最后出现**的那个日期。

    坑：题面本身含一个日期（"今天是 2025-06-04，往后数 111 天…"），
    模型的回答会把题面复述一遍，再给答案。取第一个会拿到起始日期。
    """
    text = text or ""
    best_pos, best_val = -1, None
    for m in _DATE_ISO.finditer(text):
        y, mo, d = m.groups()
        if m.start() > best_pos:
            best_pos, best_val = m.start(), f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    for m in _DATE_CN.finditer(text):
        y, mo, d = m.groups()
        if m.start() > best_pos:
            best_pos, best_val = m.start(), f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return best_val


_X_ASSIGN = re.compile(r"x\s*=\s*(-?\d[\d,]*\.?\d*)", re.I)


def _score_equation(pred: str, gold: str) -> float:
    """方程题优先找 "x = 数字"。

    坑：答案 x=0 时，模型爱写 "91(0) + 382 = 8(0) + 382" 做验算，
    取最后一个数字会抽到 382。所以先按 x= 模式抓，抓不到再退回取数。
    """
    hits = _X_ASSIGN.findall(pred or "")
    if hits:
        try:
            got = float(hits[-1].replace(",", ""))
            want = float(gold)
            return 1.0 if abs(got - want) <= max(1e-9, abs(want) * 1e-6) else 0.0
        except ValueError:
            pass
    return _score_number(pred, gold)


def _score_date(pred: str, gold: str) -> float:
    return 1.0 if _norm_date(pred) == gold else 0.0


def _score_text(pred: str, gold: str) -> float:
    """进制题：忽略空格和大小写，精确比对。"""
    p = re.sub(r"[\s,，。.]", "", (pred or "")).lower()
    return 1.0 if p and p == gold.lower() else 0.0


def _score_sudoku(pred: str, gold: str) -> float:
    """数独题：只认 1-4 的数字，取最后 16 个比对。

    模型爱写"第一行 1 2 3 4，第二行……"，中间的数字噪声不可避免，
    所以从尾部取——最终答案一定在最后。
    """
    digits = re.findall(r"[1-4]", pred or "")
    if len(digits) < 16:
        return 0.0
    return 1.0 if "".join(digits[-16:]) == gold else 0.0


SCORERS = {
    "basic_arithmetic": _score_number,
    "simple_equations": _score_equation,
    "date_math": _score_date,
    "percent_discount": _score_number,
    "base_conversion": _score_text,
    "maze_grid": _score_number,
    "sudoku_4x4": _score_sudoku,
    "n_queens": _score_number,
}


def score(family: str, pred: str, gold: str) -> float:
    fn = SCORERS.get(family)
    return fn(pred, gold) if fn else 0.0


# ---------------- 题族生成 ----------------

def _gen_arithmetic(rng: random.Random, n: int) -> list[Task]:
    """大数混合运算。

    注意：一开始我用的是四位数乘法，结果 9B 模型靠分步推导能全做对（基线 1.0），
    完全没有改进空间。所以位数必须大到"心算必错"——六位数乘五位数，
    人写代码一行就出来了，靠脑子算必翻车。这就是给 harness 留的缝。
    """
    out = []
    for _ in range(n):
        a = rng.randint(120_000, 980_000)   # 6 位
        b = rng.randint(11_000, 97_000)     # 5 位
        c = rng.randint(120_000, 890_000)   # 6 位
        d = rng.randint(11_000, 79_000)     # 5 位
        e = rng.randint(1_200, 8_900)
        style = rng.choice(["m1", "m2", "m3"])
        if style == "m1":
            q, val = f"计算：{a} × {b} + {c} - {e}", a * b + c - e
        elif style == "m2":
            q, val = f"计算：({a} + {c}) × {b} - {d}", (a + c) * b - d
        else:
            q, val = f"计算：{a} × {b} - {c} × {d}", a * b - c * d
        out.append(Task("basic_arithmetic", q + " 的值是多少？", str(val)))
    return out


def _gen_equations(rng: random.Random, n: int) -> list[Task]:
    """两边都带 x 的一元一次方程：必须移项再做大数除法，心算容易翻车。"""
    out = []
    for _ in range(n):
        a = rng.randint(31, 97)
        c = rng.randint(3, 29)
        if a == c:
            c = a + 1
        x = rng.randint(-40, 40)
        b = rng.randint(-900, 900)
        d = (a - c) * x + b
        sb = f"+ {b}" if b >= 0 else f"- {abs(b)}"
        sd = f"+ {d}" if d >= 0 else f"- {abs(d)}"
        q = f"解方程：{a}x {sb} = {c}x {sd}，求 x 的值。"
        out.append(Task("simple_equations", q, str(x)))
    return out


def _gen_dates(rng: random.Random, n: int) -> list[Task]:
    """日期推算：几乎不可能心算，必须写代码。"""
    import datetime as dt

    out = []
    base0 = dt.date(2025, 1, 1)
    for _ in range(n):
        base = base0 + dt.timedelta(days=rng.randint(0, 700))
        step = rng.choice([-1, 1]) * rng.randint(60, 420)
        target = base + dt.timedelta(days=step)
        verb = "往后数" if step > 0 else "往前数"
        q = f"今天是 {base.isoformat()}，{verb} {abs(step)} 天是几月几号？"
        out.append(Task("date_math", q, target.isoformat()))
    return out


def _gen_discount(rng: random.Random, n: int) -> list[Task]:
    """打折计算：**故意不加入训练题族**，只用来检验"换一种问法还灵不灵"。

    题面和那三族完全不同（没有"计算："前缀，没有"的值是多少"结尾），
    但一样是"心算必错、写行代码就对"。真学会了就还能对，只会背格式就会掉回去。
    """
    out = []
    for _ in range(n):
        price = rng.randrange(100_000, 999_999) * 10   # 一定是 10 的倍数，答案是整数
        disc = rng.randint(3, 9)
        q = f"某商品原价 {price} 元，现在打 {disc} 折出售，现价是多少元？"
        out.append(Task("percent_discount", q, str(price * disc // 10)))
    return out


def _gen_base(rng: random.Random, n: int) -> list[Task]:
    """进制转换：也**不加入训练题族**。

    这一族的基线应该接近 0（模型不可能心算 12 位数的 7 进制），
    用来检验"闭环是不是真学会了遇到难题就写代码"。
    """
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    for _ in range(n):
        num = rng.randrange(10**8, 10**12)
        base = rng.choice([7, 9, 11, 13])
        x, s = num, ""
        while x:
            s = digits[x % base] + s
            x //= base
        q = f"把十进制数 {num} 转换成 {base} 进制，只回答转换后的结果。"
        out.append(Task("base_conversion", q, s))
    return out


# ---------------- 难题族：光"把题面翻译成公式"不够，得先想出算法 ----------------

def _bfs(grid: list[list[str]], start: tuple[int, int]) -> dict[tuple[int, int], int]:
    """返回从 start 到所有可达格子的最短步数。"""
    from collections import deque

    h, w = len(grid), len(grid[0])
    dist = {start: 0}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in dist and grid[ny][nx] != "#":
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return dist


def _carve_maze(rng: random.Random, w: int, h: int) -> list[list[str]]:
    """标准深度优先挖迷宫：只在奇数坐标之间打通，保证任意两点连通。

    挖完后再随机多开 18% 的墙——纯 DFS 迷宫是一棵树，任意两点只有一条路，
    顺着走就能数出来，不用搜索。多开墙才有环路和死路，逼着写 BFS。
    """
    g = [["#"] * w for _ in range(h)]
    g[1][1] = "."
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        cand = []
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 1 <= nx < w - 1 and 1 <= ny < h - 1 and g[ny][nx] == "#":
                cand.append((nx, ny, dx // 2, dy // 2))
        if not cand:
            stack.pop()
            continue
        nx, ny, mx, my = rng.choice(cand)
        g[y + my][x + mx] = "."
        g[ny][nx] = "."
        stack.append((nx, ny))

    inner = [(x, y) for y in range(1, h - 1) for x in range(1, w - 1) if g[y][x] == "#"]
    for x, y in inner:
        if rng.random() < 0.18:
            g[y][x] = "."
    return g


def _gen_maze(rng: random.Random, n: int) -> list[Task]:
    """字符画迷宫，问最短步数。

    为什么这题必须写代码：9x9 迷宫要走 20~40 步，人眼都数不清，
    更别说语言模型"看着图心算"。唯一的路是写 BFS。
    """
    out = []
    for _ in range(n):
        for _attempt in range(50):
            w = rng.choice([7, 9])
            h = rng.choice([7, 9])
            g = _carve_maze(rng, w, h)
            pts = [(x, y) for y in range(h) for x in range(w) if g[y][x] == "."]
            d0 = _bfs(g, pts[0])
            far_a = max(d0, key=d0.get)
            d2 = _bfs(g, far_a)
            far_b = max(d2, key=d2.get)
            dist = d2[far_b]
            if not (10 <= dist <= 40):
                continue
            g[far_a[1]][far_a[0]] = "S"
            g[far_b[1]][far_b[0]] = "E"
            body = "\n".join("".join(row) for row in g)
            q = (
                "下面是一个迷宫。# 是墙，. 是通路，S 是起点，E 是终点。\n"
                "只能上下左右走，不能斜着走。\n"
                f"{body}\n"
                "从 S 到 E 至少需要走几步？"
            )
            out.append(Task("maze_grid", q, str(dist)))
            break
    return out


_S4_BASE = [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]]


def _s4_solve(grid: list[list[int]], limit: int = 2) -> list[list[list[int]]]:
    """4x4 数独回溯，最多找 limit 个解（用来判唯一）。"""
    res: list[list[list[int]]] = []

    def ok(r: int, c: int, v: int) -> bool:
        for i in range(4):
            if grid[r][i] == v or grid[i][c] == v:
                return False
        br, bc = (r // 2) * 2, (c // 2) * 2
        for i in range(br, br + 2):
            for j in range(bc, bc + 2):
                if grid[i][j] == v:
                    return False
        return True

    def dfs(pos: int) -> None:
        if len(res) >= limit:
            return
        while pos < 16 and grid[pos // 4][pos % 4] != 0:
            pos += 1
        if pos == 16:
            res.append([row[:] for row in grid])
            return
        r, c = pos // 4, pos % 4
        for v in range(1, 5):
            if ok(r, c, v):
                grid[r][c] = v
                dfs(pos + 1)
                grid[r][c] = 0
                if len(res) >= limit:
                    return

    dfs(0)
    return res


def _gen_sudoku(rng: random.Random, n: int) -> list[Task]:
    """4x4 数独，挖 9~12 格，保证唯一解。

    为什么这题必须写代码：4x4 虽小，但"每个数独都要试错验证"，
    模型靠猜第一行就崩。写回溯 25 行，答案绝对可靠。
    """
    out = []
    for _ in range(n):
        # 随机造一个合法终盘：换行、换列、换数字都还是合法解
        rows = [0, 1, 2, 3]
        rng.shuffle(rows[:2])
        rng.shuffle(rows[2:])
        perm_r = rows
        cols = [0, 1, 2, 3]
        rng.shuffle(cols[:2])
        rng.shuffle(cols[2:])
        perm_c = cols
        digits = [1, 2, 3, 4]
        rng.shuffle(digits)
        full = [[digits[_S4_BASE[perm_r[r]][perm_c[c]] - 1] for c in range(4)] for r in range(4)]

        for _attempt in range(200):
            g = [row[:] for row in full]
            holes = rng.sample(range(16), rng.randint(9, 12))
            for p in holes:
                g[p // 4][p % 4] = 0
            if len(_s4_solve([row[:] for row in g])) != 1:
                continue
            body = "\n".join(" ".join(str(v) for v in row) for row in g)
            q = (
                "下面是 4x4 数独：每行、每列、每个 2x2 的宫里都要填 1 到 4，且不能重复。\n"
                "0 表示空格。\n"
                f"{body}\n"
                "请填完整个棋盘。"
            )
            answer = "".join(str(v) for row in full for v in row)
            out.append(Task("sudoku_4x4", q, answer))
            break
    return out


_QUEENS_CACHE: dict[int, int] = {}


def _queens_count(n: int) -> int:
    """N 皇后方案数（回溯计数，算一次缓存）。"""
    if n in _QUEENS_CACHE:
        return _QUEENS_CACHE[n]
    cols: set[int] = set()
    d1: set[int] = set()
    d2: set[int] = set()
    cnt = 0

    def dfs(r: int) -> None:
        nonlocal cnt
        if r == n:
            cnt += 1
            return
        for c in range(n):
            if c in cols or (r - c) in d1 or (r + c) in d2:
                continue
            cols.add(c)
            d1.add(r - c)
            d2.add(r + c)
            dfs(r + 1)
            cols.remove(c)
            d1.remove(r - c)
            d2.remove(r + c)

    dfs(0)
    _QUEENS_CACHE[n] = cnt
    return cnt


def _gen_queens(rng: random.Random, n: int) -> list[Task]:
    """N 皇后方案数，N 取 10~13。

    为什么不用 8：8 皇后=92 太出名，模型可能直接背出来。
    10 以上没有背诵价值，只能老老实实写回溯。
    """
    out = []
    for _ in range(n):
        k = rng.choice([10, 11, 12, 13])
        q = (
            f"在 {k}×{k} 的棋盘上放 {k} 个皇后，要求任意两个皇后都不在同一行、"
            f"同一列或同一条对角线上。一共有多少种不同的摆法？"
        )
        out.append(Task("n_queens", q, str(_queens_count(k))))
    return out


GENERATORS = {
    "basic_arithmetic": _gen_arithmetic,
    "simple_equations": _gen_equations,
    "date_math": _gen_dates,
    "percent_discount": _gen_discount,   # 保留题型：不参与改进，只用来考
    "base_conversion": _gen_base,        # 保留题型：基线接近 0，最能看出有没有真迁移
    "maze_grid": _gen_maze,              # 难题族：要写 BFS
    "sudoku_4x4": _gen_sudoku,           # 难题族：要写回溯
    "n_queens": _gen_queens,             # 难题族：要写回溯计数
}


def generate(family: str, size: int, seed: int) -> list[Task]:
    return GENERATORS[family](random.Random(seed), size)
