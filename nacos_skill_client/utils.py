"""工具函数封装。

已移除 LLM 调用相关功能（create_llm_client, call_llm, stream 等）。
保留通用的文本/路径工具。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


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


def extract_frontmatter_content(content: str) -> dict[str, str]:
    """从 Markdown 内容中提取 frontmatter。

    Args:
        content: Markdown 文档内容。

    Returns:
        dict 包含 name/description，未找到 frontmatter 返回空 dict。
    """
    if not content:
        return {}
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?', content, re.DOTALL)
    if not match:
        return {}
    fm_content = match.group(1)
    result: dict[str, str] = {}
    for line in fm_content.split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in ('name', 'description'):
                result[key] = value
    return result


def extract_body(content: str) -> str:
    """从 Markdown 内容中提取 body（去除 YAML frontmatter）。

    Args:
        content: Markdown 文档内容。

    Returns:
        去除 frontmatter 后的 body 内容。
    """
    if not content:
        return ""
    match = re.match(r'^---\s*\n.*?\n---\s*\n(.*)$', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content.strip()
