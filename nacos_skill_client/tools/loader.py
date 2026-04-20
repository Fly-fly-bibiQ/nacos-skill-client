"""NacosToolLoader — 将 Nacos Skill 转换为 LangChain Tool。

核心职责：
1. 扫描 Nacos 中所有可用 Skill 的元数据（name + description）
2. 将每个 Skill 动态转换为 LangChain Tool（@tool / StructuredTool）
3. 缓存已注册 Tools，避免重复加载
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.tools import StructuredTool

from nacos_skill_client.client import NacosSkillClient, _extract_body, _parse_frontmatter
from nacos_skill_client.config import Config
from nacos_skill_client.models import SkillMetadata, SkillItem

logger = logging.getLogger(__name__)


class NacosToolRegistry:
    """Tool 注册中心 — 管理已注册的 LangChain Tools。

    支持缓存、刷新、查询。
    """

    def __init__(self) -> None:
        self._tools: dict[str, StructuredTool] = {}
        self._last_loaded: float = 0.0
        self._load_count: int = 0

    @property
    def tools(self) -> dict[str, StructuredTool]:
        """所有已注册的 Tools。"""
        return dict(self._tools)

    @property
    def loaded_count(self) -> int:
        """已注册 Tool 数量。"""
        return len(self._tools)

    @property
    def last_loaded_timestamp(self) -> float:
        """上次加载时间戳。"""
        return self._last_loaded

    def get_tool(self, name: str) -> StructuredTool | None:
        """按名称获取已注册的 Tool。"""
        return self._tools.get(name)

    def get_all_names(self) -> list[str]:
        """获取所有已注册 Tool 名称。"""
        return list(self._tools.keys())

    def add(self, tool: StructuredTool, metadata: SkillMetadata | None = None) -> None:
        """注册一个 Tool。"""
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s (desc: %s)", tool.name, tool.description[:80] if tool.description else "")

    def remove(self, name: str) -> bool:
        """移除一个 Tool。"""
        if name in self._tools:
            del self._tools[name]
            logger.info("Removed tool: %s", name)
            return True
        return False

    def clear(self) -> None:
        """清空所有 Tools。"""
        count = len(self._tools)
        self._tools.clear()
        self._last_loaded = 0.0
        self._load_count = 0
        logger.info("Cleared %d tools", count)

    def touch(self) -> None:
        """标记已加载时间。"""
        self._last_loaded = time.time()
        self._load_count += 1


class NacosToolLoader:
    """将 Nacos Skill 转换为 LangChain Tool。

    典型用法::

        loader = NacosToolLoader(client, config)
        tools = loader.load_all_tools()
        # tools: list[StructuredTool]
    """

    def __init__(
        self,
        client: NacosSkillClient,
        config: Config,
    ) -> None:
        """初始化 Loader。

        Args:
            client: Nacos Skill 客户端实例。
            config: 应用配置实例。
        """
        self.client = client
        self.config = config
        self.registry = NacosToolRegistry()
        self._max_skills: int = getattr(config, 'agent', None).__dict__.get('max_skills_to_load', 50) \
            if hasattr(config, 'agent') and config.agent else 50

    def load_all_tools(self, namespace_id: str | None = None) -> list[StructuredTool]:
        """扫描所有 Skill 并注册为 LangChain Tools。

        Args:
            namespace_id: 可选的命名空间过滤。

        Returns:
            注册好的 StructuredTool 列表。
        """
        self.registry.clear()

        # 1. 扫描元数据
        skills = self._scan_skills_metadata(namespace_id)
        logger.info("Discovered %d skills, loading tools...", len(skills))

        # 2. 为每个 Skill 创建 Tool
        tools: list[StructuredTool] = []
        for meta in skills:
            try:
                tool = self._create_tool_from_skill(meta)
                if tool:
                    tools.append(tool)
                    self.registry.add(tool, meta)
            except Exception as exc:
                logger.warning("Failed to create tool for skill '%s': %s", meta.name, exc)

        self.registry.touch()
        logger.info("Loaded %d/%d tools", len(tools), len(skills))
        return tools

    def reload_tools(self, namespace_id: str | None = None) -> dict[str, int]:
        """重新加载所有 Tools（清空后重建）。

        Returns:
            {"loaded": int, "total": int, "time_ms": float}
        """
        start = time.time()
        self.registry.clear()

        skills = self._scan_skills_metadata(namespace_id)
        loaded = 0
        for meta in skills:
            try:
                tool = self._create_tool_from_skill(meta)
                if tool:
                    self.registry.add(tool, meta)
                    loaded += 1
            except Exception as exc:
                logger.warning("Failed to reload tool for '%s': %s", meta.name, exc)

        self.registry.touch()
        elapsed_ms = (time.time() - start) * 1000
        return {"loaded": loaded, "total": len(skills), "time_ms": round(elapsed_ms, 1)}

    def get_system_prompt(self) -> str:
        """生成 Agent 的 system prompt，包含所有可用 Tool 的描述。

        Returns:
            System prompt 字符串。
        """
        tools = self.registry.tools
        if not tools:
            return "You are a helpful assistant."

        tool_descriptions = []
        for name, tool in sorted(tools.items()):
            desc = tool.description or ""
            tool_descriptions.append(f"- **{name}**: {desc}")

        return (
            "You are a helpful assistant that can use tools to complete tasks.\n\n"
            "You have access to the following tools:\n\n"
            + "\n".join(tool_descriptions)
            + "\n\nSelect the appropriate tool for the user's request. "
            "If no tool is needed, answer directly."
        )

    # ------------------------------------------------------------------ #
    #  私有方法
    # ------------------------------------------------------------------ #

    def _scan_skills_metadata(self, namespace_id: str | None = None) -> list[SkillMetadata]:
        """扫描所有可用 Skill 的元数据（复用 client 现有逻辑）。"""
        return self.client.scan_skills_metadata(
            namespace_id=namespace_id,
            max_count=self._max_skills,
        )

    def _create_tool_from_skill(self, metadata: SkillMetadata) -> StructuredTool | None:
        """将单个 Skill 元数据转换为 LangChain StructuredTool。

        流程：
        1. 获取 Skill 的 frontmatter（name + description）
        2. 获取 SKILL.md 的 body（instructions）
        3. 构造动态工具函数
        4. 返回 StructuredTool

        Args:
            metadata: Skill 元数据。

        Returns:
            StructuredTool 或 None（加载失败时）。
        """
        # 1. 从 Nacos 获取 SKILL.md 内容
        skill_md = self.client.get_skill_md(
            name=metadata.name,
            namespace_id=metadata.skill_path.parts[1] if len(metadata.skill_path.parts) > 1 else None,
        )

        frontmatter = {}
        instructions = ""
        if skill_md and "content" in skill_md:
            frontmatter = skill_md.get("frontmatter", {})
            instructions = _extract_body(skill_md["content"])

        # 2. 确定 Tool 描述（优先 frontmatter description，其次 metadata description）
        description = frontmatter.get("description", metadata.description or instructions[:200] or metadata.name)

        # 3. 构造动态工具函数
        def _tool_func(
            query: str = "",
            _name: str = metadata.name,
            _instructions: str = instructions,
        ) -> str:
            """Tool 执行函数。"""
            if not _instructions:
                return f"Skill '{_name}' has no instructions. Query: {query}"
            return f"[{_name}]\n\nInstructions: {_instructions}\n\nUser query: {query}"

        # 4. 返回 StructuredTool
        return StructuredTool.from_function(
            name=metadata.name,
            description=description,
            func=_tool_func,
            coroutine=None,  # 同步工具，不需要异步
        )
