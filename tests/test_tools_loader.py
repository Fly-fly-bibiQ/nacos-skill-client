"""Tests for NacosToolLoader and NacosToolRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import StructuredTool

from nacos_skill_client.config import Config
from nacos_skill_client.models import SkillMetadata
from nacos_skill_client.tools.loader import NacosToolLoader, NacosToolRegistry


class TestNacosToolRegistry:
    """测试 Tool 注册中心。"""

    def test_initial_state(self):
        reg = NacosToolRegistry()
        assert reg.loaded_count == 0
        assert len(reg.tools) == 0
        assert reg.get_tool("nonexistent") is None

    def test_add_tool(self):
        reg = NacosToolRegistry()
        tool = StructuredTool.from_function(
            name="test_tool",
            description="A test tool",
            func=lambda x: x,
        )
        meta = SkillMetadata(name="test_tool", description="A test tool", skill_path=MagicMock())
        reg.add(tool, meta)
        assert reg.loaded_count == 1
        assert reg.get_tool("test_tool") is tool

    def test_remove_tool(self):
        reg = NacosToolRegistry()
        tool = StructuredTool.from_function(
            name="test_tool",
            description="A test tool",
            func=lambda x: x,
        )
        reg.add(tool)
        assert reg.remove("test_tool") is True
        assert reg.loaded_count == 0
        assert reg.remove("nonexistent") is False

    def test_clear(self):
        reg = NacosToolRegistry()
        tool = StructuredTool.from_function(
            name="test_tool",
            description="A test tool",
            func=lambda x: x,
        )
        reg.add(tool)
        reg.clear()
        assert reg.loaded_count == 0
        assert reg.last_loaded_timestamp == 0.0

    def test_touch_updates_timestamp(self):
        reg = NacosToolRegistry()
        import time
        time_before = time.time()
        reg.touch()
        assert reg.last_loaded_timestamp >= time_before

    def test_get_all_names(self):
        reg = NacosToolRegistry()
        tool1 = StructuredTool.from_function(
            name="tool_a",
            description="Tool A",
            func=lambda x: x,
        )
        tool2 = StructuredTool.from_function(
            name="tool_b",
            description="Tool B",
            func=lambda x: x,
        )
        reg.add(tool1)
        reg.add(tool2)
        names = reg.get_all_names()
        assert "tool_a" in names
        assert "tool_b" in names
        assert len(names) == 2

    def test_tools_returns_copy(self):
        reg = NacosToolRegistry()
        tool = StructuredTool.from_function(
            name="test",
            description="test",
            func=lambda x: x,
        )
        reg.add(tool)
        tools_copy = reg.tools
        tools_copy["new_tool"] = tool
        assert "new_tool" not in reg.tools

    def test_add_multiple_tools(self):
        reg = NacosToolRegistry()
        for i in range(5):
            tool = StructuredTool.from_function(
                name=f"tool_{i}",
                description=f"Tool {i}",
                func=lambda x, n=i: x,
            )
            reg.add(tool)
        assert reg.loaded_count == 5
        assert reg.get_all_names() == ["tool_0", "tool_1", "tool_2", "tool_3", "tool_4"]


class TestNacosToolLoader:
    """测试 NacosToolLoader。"""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.scan_skills_metadata.return_value = [
            SkillMetadata(
                name="weather_check",
                description="查询天气信息",
                skill_path=MagicMock(),
            ),
            SkillMetadata(
                name="code_executor",
                description="执行代码",
                skill_path=MagicMock(),
            ),
        ]
        client.get_skill_md.return_value = {
            "content": "---\nname: test\ndescription: test\n---\nThis is the instruction content.",
            "frontmatter": {"name": "test", "description": "test"},
        }
        return client

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.agent.max_skills_to_load = 50
        config.agent.enabled = False
        config.agent.model_name = "gpt-4o-mini"
        config.agent.temperature = 0.0
        config.agent.llm_provider = "openai"
        config.agent.agent_type = "tool-calling"
        config.llm.base_url = "http://localhost:8000/v1"
        config.llm.api_key = "test_key"
        return config

    def test_init(self, mock_client, mock_config):
        loader = NacosToolLoader(mock_client, mock_config)
        assert loader.client is mock_client
        assert loader.config is mock_config
        assert isinstance(loader.registry, NacosToolRegistry)
        assert loader._max_skills == 50

    def test_load_all_tools(self, mock_client, mock_config):
        loader = NacosToolLoader(mock_client, mock_config)
        tools = loader.load_all_tools()

        assert len(tools) == 2
        assert all(isinstance(t, StructuredTool) for t in tools)
        tool_names = [t.name for t in tools]
        assert "weather_check" in tool_names
        assert "code_executor" in tool_names
        assert loader.registry.loaded_count == 2

    def test_get_system_prompt(self, mock_client, mock_config):
        loader = NacosToolLoader(mock_client, mock_config)
        # Without loading, system prompt should be minimal
        prompt = loader.get_system_prompt()
        assert "You are a helpful assistant" in prompt

        # After loading
        tools = loader.load_all_tools()
        prompt = loader.get_system_prompt()
        assert "weather_check" in prompt
        assert "code_executor" in prompt
        # Tool description comes from frontmatter (which is "test") not metadata
        # The prompt should contain the loaded tool descriptions
        assert "test" in prompt.lower() or "查询" in prompt or "执行" in prompt

    def test_reload_tools(self, mock_client, mock_config):
        loader = NacosToolLoader(mock_client, mock_config)
        # First load
        tools1 = loader.load_all_tools()
        assert len(tools1) == 2

        # Reload
        result = loader.reload_tools()
        assert result["loaded"] == 2
        assert result["total"] == 2
        assert "time_ms" in result
        assert isinstance(result["time_ms"], float)

        # Verify tools are still available
        assert loader.registry.loaded_count == 2

    def test_reload_clears_previous_state(self, mock_client, mock_config):
        loader = NacosToolLoader(mock_client, mock_config)
        loader.load_all_tools()
        # Simulate clearing and changing skills
        mock_client.scan_skills_metadata.return_value = [
            SkillMetadata(
                name="new_skill",
                description="New skill",
                skill_path=MagicMock(),
            ),
        ]
        result = loader.reload_tools()
        assert result["loaded"] == 1
        assert loader.registry.loaded_count == 1
        assert "new_skill" in loader.registry.get_all_names()
        assert "weather_check" not in loader.registry.get_all_names()

    def test_load_all_tools_with_exception(self, mock_client, mock_config):
        """测试加载时某个 Skill 失败不影响其他 Skills。"""
        mock_client.get_skill_md.side_effect = [
            {"content": "---\nname: w\ndescription: w\n---\nWeather instructions.", "frontmatter": {}},
            Exception("Network error"),
        ]
        loader = NacosToolLoader(mock_client, mock_config)
        tools = loader.load_all_tools()
        assert len(tools) == 1
        assert tools[0].name == "weather_check"

    def test_create_tool_from_skill_no_content(self, mock_client, mock_config):
        """测试 Skill 没有 SKILL.md 内容时。"""
        mock_client.get_skill_md.return_value = None
        loader = NacosToolLoader(mock_client, mock_config)
        meta = SkillMetadata(
            name="no_content_skill",
            description="No content",
            skill_path=MagicMock(),
        )
        tool = loader._create_tool_from_skill(meta)
        assert tool is not None
        assert tool.name == "no_content_skill"
        # The tool should still have a description
        assert tool.description == "No content"

    def test_create_tool_from_skill_frontmatter_priority(self, mock_client, mock_config):
        """测试 frontmatter description 优先于 metadata description。"""
        mock_client.get_skill_md.return_value = {
            "content": "---\nname: weather\ndescription: This is frontmatter description\n---\nbody content.",
            "frontmatter": {"name": "weather", "description": "This is frontmatter description"},
        }
        loader = NacosToolLoader(mock_client, mock_config)
        meta = SkillMetadata(
            name="weather",
            description="metadata description",
            skill_path=MagicMock(),
        )
        tool = loader._create_tool_from_skill(meta)
        assert tool is not None
        assert "frontmatter" in tool.description.lower()

    def test_max_skills_from_config(self, mock_client):
        """测试 _max_skills 从配置读取。"""
        config = MagicMock()
        config.agent.max_skills_to_load = 10
        loader = NacosToolLoader(mock_client, config)
        assert loader._max_skills == 10

    def test_system_prompt_empty_when_no_tools(self):
        """测试没有注册 Tools 时 system prompt 为基本版本。"""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_config.agent = MagicMock()
        mock_config.agent.max_skills_to_load = 50
        loader = NacosToolLoader(mock_client, mock_config)
        prompt = loader.get_system_prompt()
        assert "You are a helpful assistant" in prompt
        assert "weather_check" not in prompt

    def test_system_prompt_contains_multiple_tools(self, mock_client, mock_config):
        """测试 system prompt 包含多个 Tool 描述。"""
        loader = NacosToolLoader(mock_client, mock_config)
        loader.load_all_tools()
        prompt = loader.get_system_prompt()
        assert "**weather_check**" in prompt
        assert "**code_executor**" in prompt
        # descriptions may come from frontmatter or metadata
        # verify all tool names appear
        assert len(prompt.split("\n")) > 5  # has multiple tool lines
