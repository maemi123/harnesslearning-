"""第 2 层 harness —— 日期加减/算术/线性方程走 py() 精确计算，其余退回 ask。"""

import re


def _extract_expr(q):
    """从题干里尽量提取一个纯算术表达式。提取不到返回 None。"""
    cand = q
    m = re.search(r"[:：]\s*(.+)$", cand)
    if m:
        cand = m.group(1)
    for tail in ["的值是多少", "的值", "值是多少", "等于多少", "是多少", "？", "?"]:
        cand = cand.replace(tail, " ")
    cand = cand.replace("×", "*").replace("÷", "/").replace("−", "-").replace("—", "-")
    cand = cand.replace("（", "(").replace("）", ")")
    cand = cand.replace("，", "").replace(",", "").replace("　", " ")
    cand = re.sub(r"[^0-9+\-*/().\s]", "", cand)
    cand = cand.strip()
    if not re.fullmatch(r"[0-9+\-*/().\s]+", cand):
        return None
    if not re.search(r"\d", cand):
        return None
    if not re.search(r"[+\-*/]", cand):
        return None
    if cand.count("(") != cand.count(")"):
        return None
    return cand


def _norm_num(val):
    """把 py 输出规整成答案字符串；不靠谱返回 None。"""
    if val is None:
        return None
    out = val.strip()
    if not out or out.startswith("[ERR]"):
        return None
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if len(lines) != 1:
        return None
    val = lines[0]
    if not re.fullmatch(r"-?\d+(\.\d+)?", val):
        return None
    if "." in val:
        f = float(val)
        if f == int(f):
            val = str(int(f))
        else:
            return None
    return val


def _try_date(question, py):
    """解析日期加减题，用 datetime 精确计算。返回答案或 None。"""
    q = question.strip()
    md = re.search(r"(\d{4})\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})", q)
    if not md:
        return None
    y, mo, d = int(md.group(1)), int(md.group(2)), int(md.group(3))
    if re.search(r"往前|向前|之前|以前|减去|前数|倒推", q):
        sign = -1
    elif re.search(r"往后|向后|之后|以后|加上|后数|顺推", q):
        sign = 1
    else:
        return None
    mt = re.search(r"(\d+)\s*天", q)
    if not mt:
        return None
    n = int(mt.group(1))
    offset = sign * n
    code = (
        "import datetime\n"
        "try:\n"
        "    dt = datetime.date(%d, %d, %d) + datetime.timedelta(days=%d)\n"
        "    print(dt.strftime('%%Y-%%m-%%d'))\n"
        "except Exception as e:\n"
        "    print('[ERR]', e)\n"
    ) % (y, mo, d, offset)
    out = py(code)
    if out is None:
        return None
    out = out.strip()
    if not out or out.startswith("[ERR]"):
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", out):
        return None
    return out


def _solve_linear(question, py):
    """解析一元一次线性方程 ax+b=cx+d（整系数）并求解。返回答案或 None。"""
    q = question.strip()
    if not re.search(r"解方程|方程|求\s*x|求x|求\s*X", q):
        return None
    # 取冒号后面
    m = re.search(r"[:：]\s*(.+)$", q)
    body = m.group(1) if m else q
    # 去掉末尾求值说明
    body = re.sub(r"[，,。；;]?\s*求.*$", "", body)
    body = body.replace("−", "-").replace("—", "-").replace("＝", "=")
    body = body.replace("（", "(").replace("）", ")")
    body = body.replace("　", " ")
    # 只允许字符集
    if not re.fullmatch(r"[0-9xX+\-*/().=\s]+", body):
        return None
    if body.count("=") != 1:
        return None
    lhs, rhs = body.split("=")
    lhs = lhs.strip()
    rhs = rhs.strip()
    if not lhs or not rhs:
        return None
    # 转成 Python 表达式求系数：把 x 当变量，用 eval 思想但实际用 py()。
    # 做法：分别对 x=0 和 x=1 求 lhs-rhs，得到一次函数 m*x + c。
    def _mk(side):
        # 补乘号：数字/右括号 后接 x，或 x 后接数字/左括号
        s = re.sub(r"(\d)\s*([xX])", r"\1*\2", side)
        s = re.sub(r"([xX])\s*(\d)", r"\1*\2", s)
        s = re.sub(r"([xX])\s*\(", r"\1*(", s)
        s = re.sub(r"\)\s*([xX])", r")*\1", s)
        s = s.replace("X", "x")
        return s
    l = _mk(lhs)
    r = _mk(rhs)
    if not re.fullmatch(r"[0-9x+\-*/().\s]+", l) or not re.fullmatch(r"[0-9x+\-*/().\s]+", r):
        return None
    code = (
        "def f(x):\n"
        "    try:\n"
        "        return (%s) - (%s)\n"
        "    except Exception as e:\n"
        "        raise e\n"
        "try:\n"
        "    c0 = f(0)\n"
        "    c1 = f(1)\n"
        "    m = c1 - c0\n"
        "    if m == 0:\n"
        "        print('[ERR] no_unique')\n"
        "    else:\n"
        "        x = -c0 / m\n"
        "        print(repr(x))\n"
        "except Exception as e:\n"
        "    print('[ERR]', e)\n"
    ) % (l, r)
    out = py(code)
    if out is None:
        return None
    out = out.strip()
    if not out or out.startswith("[ERR]"):
        return None
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    if len(lines) != 1:
        return None
    s = lines[0]
    try:
        f = float(s)
    except Exception:
        return None
    if f == int(f):
        return str(int(f))
    return None


def run(question, ask, py):
    try:
        q = question.strip()

        # 1) 日期加减
        try:
            date_ans = _try_date(q, py)
            if date_ans is not None:
                return date_ans
        except Exception:
            pass

        # 2) 一元一次方程
        try:
            eq_ans = _solve_linear(q, py)
            if eq_ans is not None:
                return eq_ans
        except Exception:
            pass

        # 3) 纯算术
        if not re.search(r"计算", q):
            return ask(question)

        expr = _extract_expr(q)
        if expr:
            if re.fullmatch(r"[0-9+\-*/().\s]+", expr) and re.search(r"\d", expr) \
                    and re.search(r"[+\-*/]", expr):
                code = "print(%s)" % expr
                out = py(code)
                val = _norm_num(out)
                if val is not None:
                    return val

        return ask(question)
    except Exception:
        pass
    return ask(question)
