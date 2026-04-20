"""LLM 调用工具封装。"""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)


def create_llm_client(base_url: str, api_key: str = "dummy", timeout: int = 120) -> OpenAI:
    """创建 OpenAI 兼容的 LLM 客户端。

    Args:
        base_url: API 基础 URL，如 http://192.168.1.118:8000/v1。
        api_key: API Key。
        timeout: 超时（秒）。

    Returns:
        OpenAI 客户端实例。
    """
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def call_llm(
    client: OpenAI,
    messages: list[dict[str, str]],
    model: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    stream: bool = False,
) -> str | Any:
    """调用 LLM API 并返回文本内容。

    Args:
        client: OpenAI 客户端。
        messages: 消息列表。
        model: 模型名称。
        temperature: 温度。
        max_tokens: 最大 tokens。
        stream: 是否流式。

    Returns:
        非流式返回文本内容，流式返回事件生成器。
    """
    if stream:
        return _stream_call(client, messages, model, temperature, max_tokens)
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


def _stream_call(
    client: OpenAI,
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Any:
    """流式调用 LLM，返回 SSE 事件生成器。

    每个事件是一个字典: {"type": "content", "data": "text"}
    或 {"type": "done"}。
    """
    def event_generator():
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                yield {"type": "content", "data": chunk.choices[0].delta.content}
        yield {"type": "done"}

    return event_generator()


def build_prompt(system: str, user: str) -> list[dict[str, str]]:
    """构建标准消息列表。

    Args:
        system: system 消息内容。
        user: user 消息内容。

    Returns:
        消息列表。
    """
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
