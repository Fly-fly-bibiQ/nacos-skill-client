"""LangChain Tools 加载器。

将 Nacos Skill 转换为 LangChain Tool 对象，供 Agent 自动路由使用。
"""

from __future__ import annotations

from .loader import NacosToolLoader

__all__ = ["NacosToolLoader"]
