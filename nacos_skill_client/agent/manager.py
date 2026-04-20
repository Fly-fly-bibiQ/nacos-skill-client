"""Agent 管理器。

基于 LangChain `create_agent` API 创建和管理 Agent 实例。
支持多 LLM provider（OpenAI/Anthropic/Local）和两种 Agent 类型。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage

from nacos_skill_client.config import Config
from nacos_skill_client.tools.loader import NacosToolLoader

logger = logging.getLogger(__name__)


@dataclass
class AgentChatResult:
    """Agent 对话结果。"""
    answer: str
    tool_used: str | None = None
    thinking_steps: list[str] = field(default_factory=list)
    took_ms: float = 0.0


class AgentManager:
    """Agent 管理器 — 创建、配置和运行 LangChain Agent。

    默认状态 disabled，需显式启用。
    支持多 provider：openai（默认）、anthropic、local（litellm）。
    """

    def __init__(self, config: Config, loader: NacosToolLoader) -> None:
        """初始化 Agent 管理器。

        Args:
            config: 应用配置。
            loader: NacosToolLoader 实例。
        """
        self.config = config
        self.loader = loader
        self._agent = None
        self._enabled = self._is_agent_enabled()
        self._checkpointer = None
        self._model = None

    @property
    def enabled(self) -> bool:
        """是否启用了 Agent 模式。"""
        return self._enabled

    @property
    def is_ready(self) -> bool:
        """Agent 是否已初始化完毕可以运行。"""
        return self._enabled and self._agent is not None

    def initialize(self) -> None:
        """初始化 Agent（加载 Tools + 创建 Agent 实例）。

        如果 agent.enabled=false 则跳过。
        """
        if not self._enabled:
            logger.info("Agent is disabled in config, skipping initialization")
            return

        if self._agent is not None:
            logger.info("Agent already initialized, skipping")
            return

        logger.info("Initializing agent...")
        agent_type = self._get_agent_type()

        if agent_type == "tool-calling":
            self._initialize_tool_calling()
        else:
            # ReAct 等类型暂不实现，返回空
            logger.warning("Agent type '%s' not yet implemented", agent_type)
            return

        if self._agent is not None:
            logger.info("Agent initialized successfully")

    def _initialize_tool_calling(self) -> None:
        """使用 Tool Calling 方式初始化 Agent（推荐）。"""
        from langchain.agents import create_agent
        from langgraph.checkpoint.memory import InMemorySaver

        # 1. 加载 Tools
        tools = self.loader.registry.tools.values()
        if not tools:
            logger.warning("No tools available, agent cannot be initialized")
            return

        # 2. 初始化 LLM 模型
        self._model = self._init_model()
        if self._model is None:
            return

        # 3. 加载 Tools（实际从 registry 取，不重复创建）
        tool_list = list(tools)
        logger.info("Using %d tools for agent", len(tool_list))

        # 4. 创建 System Prompt
        system_prompt = self.loader.get_system_prompt()

        # 5. 初始化记忆
        self._checkpointer = InMemorySaver()

        # 6. 创建 Agent
        self._agent = create_agent(
            model=self._model,
            tools=tool_list,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
        )
        logger.info("Agent created with Tool Calling strategy")

    def chat(self, query: str, thread_id: str = "default") -> AgentChatResult:
        """与 Agent 对话。

        Args:
            query: 用户查询。
            thread_id: 对话线程 ID（用于记忆）。

        Returns:
            AgentChatResult 包含回答和工具使用信息。
        """
        import time

        if not self.is_ready:
            if not self._enabled:
                return AgentChatResult(
                    answer="Agent mode is disabled. Please contact administrator to enable it.",
                )
            self.initialize()
            if not self.is_ready:
                return AgentChatResult(answer="Agent is not ready. Please try again later.")

        start = time.time()
        config = {"configurable": {"thread_id": thread_id}}

        result = self._agent.invoke(
            {"messages": [HumanMessage(content=query)]},
            config=config,
        )

        elapsed_ms = (time.time() - start) * 1000

        # 解析结果
        answer = self._parse_agent_result(result)
        tool_used = self._extract_tool_used(result)
        steps = self._extract_thinking_steps(result)

        return AgentChatResult(
            answer=answer,
            tool_used=tool_used,
            thinking_steps=steps,
            took_ms=round(elapsed_ms, 1),
        )

    def reload(self) -> dict[str, Any]:
        """重新加载 Tools 并重新初始化 Agent。

        Returns:
            加载结果。
        """
        if not self._enabled:
            return {"status": "disabled", "message": "Agent is disabled"}

        reload_result = self.loader.reload_tools()

        # 清空旧 Agent
        self._agent = None
        self._model = None
        self._checkpointer = None

        # 重新初始化
        self._initialize_tool_calling()

        reload_result["status"] = "ok"
        reload_result["agent_initialized"] = self.is_ready
        return reload_result

    # ------------------------------------------------------------------ #
    #  私有方法
    # ------------------------------------------------------------------ #

    def _is_agent_enabled(self) -> bool:
        """检查 Agent 是否启用。"""
        if not hasattr(self.config, 'agent'):
            return False
        agent_cfg = self.config.agent
        return getattr(agent_cfg, 'enabled', False)

    def _get_agent_type(self) -> str:
        """获取 Agent 类型。"""
        if not hasattr(self.config, 'agent'):
            return "tool-calling"
        agent_cfg = self.config.agent
        return getattr(agent_cfg, 'agent_type', 'tool-calling') or 'tool-calling'

    def _init_model(self):
        """初始化 LLM 模型。"""
        provider = self._get_llm_provider()
        model_name = self._get_model_name()
        temperature = self._get_temperature()

        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
                base_url = self._get_llm_base_url()
                api_key = self._get_llm_api_key()
                return ChatOpenAI(
                    model=model_name,
                    temperature=temperature,
                    base_url=base_url,
                    api_key=api_key,
                )
            except Exception as exc:
                logger.error("Failed to init OpenAI model: %s", exc)
                return None
        elif provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model=model_name,
                    temperature=temperature,
                )
            except Exception as exc:
                logger.error("Failed to init Anthropic model: %s", exc)
                return None
        else:
            # 默认尝试 OpenAI 兼容接口
            try:
                from langchain_openai import ChatOpenAI
                base_url = self._get_llm_base_url()
                api_key = self._get_llm_api_key()
                return ChatOpenAI(
                    model=model_name,
                    temperature=temperature,
                    base_url=base_url,
                    api_key=api_key,
                )
            except Exception as exc:
                logger.error("Failed to init default model: %s", exc)
                return None

    def _get_llm_provider(self) -> str:
        if not hasattr(self.config, 'agent'):
            return "openai"
        return getattr(self.config.agent, 'llm_provider', 'openai') or 'openai'

    def _get_model_name(self) -> str:
        if not hasattr(self.config, 'agent'):
            return "gpt-4o-mini"
        return getattr(self.config.agent, 'model_name', 'gpt-4o-mini') or 'gpt-4o-mini'

    def _get_temperature(self) -> float:
        if not hasattr(self.config, 'agent'):
            return 0.0
        return getattr(self.config.agent, 'temperature', 0.0)

    def _get_llm_base_url(self) -> str:
        """获取 LLM 基础 URL。"""
        # Agent 配置优先级高于 LLM 配置
        if hasattr(self.config, 'agent'):
            return getattr(self.config, 'llm').base_url
        return self.config.llm.base_url

    def _get_llm_api_key(self) -> str:
        """获取 LLM API Key。"""
        if hasattr(self.config, 'agent'):
            return getattr(self.config, 'llm').api_key
        return self.config.llm.api_key

    def _parse_agent_result(self, result: dict) -> str:
        """解析 Agent 返回结果。"""
        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            return getattr(last, 'content', str(last)) if hasattr(last, 'content') else str(last)
        return "No response from agent."

    def _extract_tool_used(self, result: dict) -> str | None:
        """从结果中提取使用的工具名称。"""
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                return msg.tool_calls[0].get("name", "") if isinstance(msg.tool_calls[0], dict) else str(msg.tool_calls[0])
        return None

    def _extract_thinking_steps(self, result: dict) -> list[str]:
        """从结果中提取思考步骤。"""
        messages = result.get("messages", [])
        steps = []
        for msg in messages:
            if hasattr(msg, 'content') and hasattr(msg, 'tool_calls'):
                if msg.tool_calls:
                    tool_name = msg.tool_calls[0].get("name", "tool") if msg.tool_calls else "?"
                    steps.append(f"tool: {tool_name}")
                elif msg.content:
                    steps.append(f"thought: {msg.content[:60]}")
        return steps or ["completed"]
