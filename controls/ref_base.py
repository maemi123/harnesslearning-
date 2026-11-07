"""对照用：手写的进制转换解析器。证明题目可解、判分没错。"""

import re


def run(question, ask, py):
    m = re.search(r"十进制数\s*(\d+)\s*转换成\s*(\d+)\s*进制", question)
    if not m:
        return ask(question)
    num, base = int(m.group(1)), int(m.group(2))
    code = (
        "n = %d\n"
        "b = %d\n"
        "d = '0123456789abcdefghijklmnopqrstuvwxyz'\n"
        "s = ''\n"
        "while n:\n"
        "    s = d[n %% b] + s\n"
        "    n //= b\n"
        "print(s)\n"
    ) % (num, base)
    out = py(code)
    if out and not out.startswith("[ERR]"):
        return out.strip()
    return ask(question)
