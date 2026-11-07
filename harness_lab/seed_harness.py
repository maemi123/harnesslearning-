"""第 0 层 harness —— 最朴素的一版，也就是论文说的 seed harness。

这个文件永远不要改。每轮迭代都从它复制一份出来改。

接口约定（proposer 写的所有 harness 都必须长这样）：

    def run(question: str, ask, py) -> str

    ask(prompt) -> str   问一次 solver 模型，返回文本
    py(code)    -> str   执行一段 Python，返回 stdout（出错返回错误信息）

返回值就是最终答案字符串。
"""


def run(question, ask, py):
    return ask(question)
