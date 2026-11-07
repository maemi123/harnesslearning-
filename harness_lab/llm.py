"""最小 OpenAI 兼容客户端：只用标准库，带重试和 token 计数。"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.calls += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
            }


USAGE = Usage()


def chat(
    messages: list[dict],
    model: str,
    temperature: float = 0.6,
    max_tokens: int = 2048,
    timeout: int = 180,
    enable_thinking: bool = False,
) -> str:
    """调一次 chat/completions，返回纯文本。失败按指数退避重试。"""
    if not config.API_KEY:
        raise LLMError("没有 API key：先设置环境变量 HL_API_KEY")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        # 硅基流动的 Qwen3.5 默认开思考模式，实测单次 >180s，必须关掉
        "enable_thinking": enable_thinking,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{config.API_BASE.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = data["choices"][0]["message"]
            text = (choice.get("content") or "").strip()
            usage = data.get("usage") or {}
            USAGE.add(
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)),
            )
            return text
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            last_err = LLMError(f"HTTP {e.code}: {detail}")
            # 429 = 限流，等久一点；4xx 其他错误重试也没用
            if e.code not in (408, 409, 425, 429, 500, 502, 503, 504):
                raise last_err from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            last_err = LLMError(f"{type(e).__name__}: {e}")

        sleep = config.RETRY_BASE_SLEEP * (2**attempt)
        time.sleep(sleep)

    raise LLMError(f"重试 {config.MAX_RETRIES} 次仍失败：{last_err}")
