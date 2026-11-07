"""全局配置：改这里就能换模型、换题族、改规模。"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """从同级 .env 读密钥，免得每次在命令行里写明文。已设置的环境变量优先。"""
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# ---------- 路径 ----------
ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
DATA_DIR = ROOT / "data"
HARNESS_PATH = ROOT / "harness.py"          # 当前正在用的 harness（会被反复覆盖）
SEED_PATH = ROOT / "seed_harness.py"        # 第 0 层，永远不动，每轮从这里重建

# ---------- API（OpenAI 兼容） ----------
# 硅基流动免费档：https://cloud.siliconflow.cn
API_BASE = os.getenv("HL_API_BASE", "https://api.siliconflow.cn/v1")
API_KEY = os.getenv("HL_API_KEY", "")

# 离线模式：不调真模型，只验证管线能不能跑通（分数一定是 0，别当实验结果）
OFFLINE = os.getenv("HL_OFFLINE", "") == "1"

# 论文里 solver 是冻结的 Qwen3-8B，proposer 是 Qwen3-4B。
# 但实测硅基流动免费档上 Qwen 系列要 17s/次，GLM-4-9B 只要 3s，solver 换 GLM 快 6 倍。
# proposer 保持 4B（贴论文设定，而且每轮只调一次，慢点无所谓）。
SOLVER_MODEL = os.getenv("HL_SOLVER_MODEL", "THUDM/GLM-4-9B-0414")
PROPOSER_MODEL = os.getenv("HL_PROPOSER_MODEL", "Qwen/Qwen3-8B")

SOLVER_TEMPERATURE = 0.6
SOLVER_MAX_TOKENS = 2048
PROPOSER_TEMPERATURE = 1.0
PROPOSER_MAX_TOKENS = 8192   # 4096 不够，实测会被截断成语法错误的半截代码

# 思考模式：免费端点上开着会慢到不可用（实测单次 >180s），默认关闭。
# 如果你用的是付费端点或本地部署，可以打开试试，proposer 写代码会更强。
SOLVER_THINKING = False
PROPOSER_THINKING = False

# ---------- 题目 ----------
# 每族：前 DEV_SIZE 条给 proposer 看（也用来打分选 harness），
#       后 EVAL_SIZE 条全程锁死，只在最后算成绩。
FAMILIES = ["basic_arithmetic", "simple_equations", "date_math"]
DEV_SIZE = 20
EVAL_SIZE = 15
DATA_SEED = 42

# ---------- 迭代 ----------
MAX_ROUNDS = 8              # 论文是 10 轮，我们 8 轮够看趋势
SOLVER_CALL_BUDGET = 6      # 单题最多调几次模型（论文是 12）
PROPOSER_FEEDBACK_K = 6     # 每轮喂给 proposer 几条失败记录
HARNESS_MAX_LINES = 200     # 超过就判废，跟论文一致

# ---------- 沙箱 ----------
# 免费端点并发一高就排队变慢，超时要给宽一点，并发别开大
RUN_TIMEOUT = 180           # 单题总超时（秒）
PY_TIMEOUT = 15             # harness 内部调用 python() 的超时（秒）
PY_MAX_OUTPUT = 4000        # 代码执行返回的字符上限
WORKERS = 2                 # 并发跑题数；免费档 TPM/并发都有上限，开大反而更慢

# ---------- 重试 ----------
MAX_RETRIES = 4
RETRY_BASE_SLEEP = 3.0
