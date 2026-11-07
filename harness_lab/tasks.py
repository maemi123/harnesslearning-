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


SCORERS = {
    "basic_arithmetic": _score_number,
    "simple_equations": _score_equation,
    "date_math": _score_date,
    "percent_discount": _score_number,
    "base_conversion": _score_text,
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


GENERATORS = {
    "basic_arithmetic": _gen_arithmetic,
    "simple_equations": _gen_equations,
    "date_math": _gen_dates,
    "percent_discount": _gen_discount,   # 保留题型：不参与改进，只用来考
    "base_conversion": _gen_base,        # 保留题型：基线接近 0，最能看出有没有真迁移
}


def generate(family: str, size: int, seed: int) -> list[Task]:
    return GENERATORS[family](random.Random(seed), size)
