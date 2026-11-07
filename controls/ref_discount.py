"""对照用：手写的打折题解析器。只用来证明「题目可解、判分没错」。"""

import re


def run(question, ask, py):
    m = re.search(r"原价\s*(\d+)\s*元.*?打\s*(\d)\s*折", question)
    if m:
        price, disc = int(m.group(1)), int(m.group(2))
        if price * disc % 10 == 0:
            return str(price * disc // 10)
    return ask(question)
