"""离线假模型 —— 只有一个用途：验证管线（沙箱、跑分、评分、日志）能不能跑通。

它永远返回 "0"，所以分数注定是 0。看到非零分数说明评分器有问题，不是模型厉害。
"""

from __future__ import annotations


def chat(messages, **kwargs) -> str:
    return "0"
