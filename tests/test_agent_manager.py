"""Tests for AgentManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from nacos_skill_client.agent.manager import AgentChatResult, AgentManager
from nacos_skill_client.config import Config
from nacos_skill_client.tools.loader import NacosToolLoader


class TestAgentChatResult:
    """测试 AgentChatResult 数据类。"""

    def test_defaults(self):
        result = AgentChatResult(answer="Hello")
        assert result.answer == "Hello"
        assert result.tool_used is None
        assert result.thinking_steps == []
        assert result.took_ms == 0.0

    def test_full_values(self):
        result = AgentChatResult(
            answer="Hello",
            tool_used="weather_check",
            thinking_steps=["thought", "tool"],
            took_ms=1234.5,
        )
        assert result.answer == "Hello"
        assert result.tool_used == "weather_check"
        assert result.thinking_steps == ["thought", "tool"]
        assert result.took_ms == 1234.5


class TestAgentManagerDisabled:
    """测试 Agent 未启用时的行为。"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock(spec=Config)
        config.agent = MagicMock()
        config.agent.enabled = False
        config.agent.llm_provider = "openai"
        config.agent.model_name = "gpt-4o-mini"
        config.agent.temperature = 0.0
        config.agent.agent_type = "tool-calling"
        config.llm = MagicMock()
        config.llm.base_url = "http://localhost:8000/v1"
        config.llm.api_key = "test_key"
        return config

    @pytest.fixture
    def mock_loader(self):
        loader = MagicMock()
        loader.registry.tools = {}
        loader.get_system_prompt.return_value = "System prompt"
        return loader

    def test_init_disabled(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager.enabled is False
        assert manager.is_ready is False

    def test_initialize_does_nothing_when_disabled(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        manager.initialize()
        assert manager._agent is None
        assert manager._model is None

    def test_chat_when_disabled(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        result = manager.chat("hello")
        assert "disabled" in result.answer.lower()
        assert isinstance(result, AgentChatResult)


class TestAgentManagerEnabledNotReady:
    """测试 Agent 启用但未初始化时的行为。"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock(spec=Config)
        config.agent = MagicMock()
        config.agent.enabled = True
        config.agent.llm_provider = "openai"
        config.agent.model_name = "gpt-4o-mini"
        config.agent.temperature = 0.0
        config.agent.agent_type = "tool-calling"
        config.llm = MagicMock()
        config.llm.base_url = "http://localhost:8000/v1"
        config.llm.api_key = "test_key"
        return config

    @pytest.fixture
    def mock_loader(self):
        loader = MagicMock()
        loader.registry.tools = {}
        loader.get_system_prompt.return_value = "System prompt"
        return loader

    def test_initialize_no_tools(self, mock_config, mock_loader):
        """没有可用 Tools 时 Agent 不初始化。"""
        manager = AgentManager(mock_config, mock_loader)
        manager.initialize()
        assert manager._agent is None

    def test_reload_when_disabled(self, mock_config, mock_loader):
        mock_config.agent.enabled = False
        manager = AgentManager(mock_config, mock_loader)
        result = manager.reload()
        assert result["status"] == "disabled"


class TestAgentManagerEnabledReady:
    """测试 Agent 启用且已初始化后的行为（mock Agent）。"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock(spec=Config)
        config.agent = MagicMock()
        config.agent.enabled = True
        config.agent.llm_provider = "openai"
        config.agent.model_name = "gpt-4o-mini"
        config.agent.temperature = 0.0
        config.agent.agent_type = "tool-calling"
        config.llm = MagicMock()
        config.llm.base_url = "http://localhost:8000/v1"
        config.llm.api_key = "test_key"
        return config

    @pytest.fixture
    def mock_loader(self):
        loader = MagicMock()
        loader.get_system_prompt.return_value = "System prompt"
        return loader

    def test_initialize_with_mock_model(self, mock_config, mock_loader):
        """使用 mock 模型初始化 Agent。"""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_loader.registry.tools = {"test_tool": mock_tool}

        with patch(
            "langchain_openai.ChatOpenAI",
            return_value=MagicMock(),
        ):
            with patch(
                "langchain.agents.create_agent",
                return_value=MagicMock(),
            ):
                with patch(
                    "langgraph.checkpoint.memory.InMemorySaver",
                    return_value=MagicMock(),
                ):
                    manager = AgentManager(mock_config, mock_loader)
                    manager.initialize()
                    assert manager._agent is not None
                    assert manager.is_ready is True

    def test_chat_result_parsing(self, mock_config, mock_loader):
        """测试 Agent 结果解析。"""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_loader.registry.tools = {"test_tool": mock_tool}

        mock_agent = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "The weather is sunny."
        mock_msg.tool_calls = []
        mock_agent.invoke.return_value = {"messages": [mock_msg]}

        with patch(
            "langchain_openai.ChatOpenAI",
            return_value=MagicMock(),
        ):
            with patch(
                "langchain.agents.create_agent",
                return_value=mock_agent,
            ):
                with patch(
                    "langgraph.checkpoint.memory.InMemorySaver",
                    return_value=MagicMock(),
                ):
                    manager = AgentManager(mock_config, mock_loader)
                    manager.initialize()
                    result = manager.chat("what is the weather")

                    assert result.answer == "The weather is sunny."
                    assert isinstance(result, AgentChatResult)
                    assert isinstance(result.took_ms, float)


class TestAgentConfigDefaults:
    """测试 AgentConfig 默认值。"""

    def test_default_enabled_false(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.enabled is False

    def test_default_model_name(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.model_name == "gpt-4o-mini"

    def test_default_temperature(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.temperature == 0.0

    def test_default_agent_type(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.agent_type == "tool-calling"

    def test_default_max_skills(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.max_skills_to_load == 50

    def test_custom_values(self):
        from nacos_skill_client.config import AgentConfig
        cfg = AgentConfig(
            enabled=True,
            model_name="claude-sonnet-4-6",
            temperature=0.7,
            max_skills_to_load=100,
        )
        assert cfg.enabled is True
        assert cfg.model_name == "claude-sonnet-4-6"
        assert cfg.temperature == 0.7
        assert cfg.max_skills_to_load == 100


class TestAgentManagerGetters:
    """测试 AgentManager 的 getter 方法。"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock(spec=Config)
        config.agent = MagicMock()
        config.agent.enabled = False
        config.agent.llm_provider = "openai"
        config.agent.model_name = "gpt-4o-mini"
        config.agent.temperature = 0.5
        config.agent.agent_type = "react"
        config.llm = MagicMock()
        config.llm.base_url = "http://custom-url:8000/v1"
        config.llm.api_key = "custom_key"
        return config

    @pytest.fixture
    def mock_loader(self):
        return MagicMock()

    def test_get_llm_provider(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_llm_provider() == "openai"

    def test_get_model_name(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_model_name() == "gpt-4o-mini"

    def test_get_temperature(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_temperature() == 0.5

    def test_get_agent_type(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_agent_type() == "react"

    def test_get_llm_base_url(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_llm_base_url() == "http://custom-url:8000/v1"

    def test_get_llm_api_key(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._get_llm_api_key() == "custom_key"

    def test_is_agent_enabled_returns_false(self, mock_config, mock_loader):
        manager = AgentManager(mock_config, mock_loader)
        assert manager._is_agent_enabled() is False
