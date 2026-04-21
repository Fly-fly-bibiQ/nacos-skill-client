"""Tests for Agent API endpoints.

Covers:
- POST /api/v1/chat
- GET /api/v1/skills/tools
- POST /api/v1/skills/tools/reload
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


class TestChatEndpoint:
    """POST /api/v1/chat 端点测试。"""

    def test_disabled_agent_returns_message(self, client):
        """Agent 未启用时返回提示信息。"""
        mock_agent = MagicMock()
        mock_agent.enabled = False
        mock_agent.chat.return_value = MagicMock(
            answer="Agent disabled",
            tool_used=None,
            thinking_steps=[],
            took_ms=0,
        )

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.post("/api/v1/chat", json={"message": "hello"})

        assert resp.status_code == 200
        data = resp.json()
        assert "disabled" in data["answer"].lower()

    def test_chat_with_mock_agent(self, client):
        """测试正常 Agent 对话。"""
        mock_result = MagicMock()
        mock_result.answer = "The weather is sunny."
        mock_result.tool_used = "weather_check"
        mock_result.thinking_steps = ["tool: weather_check"]
        mock_result.took_ms = 1234.5

        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.chat.return_value = mock_result

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.post("/api/v1/chat", json={
                "message": "what is the weather",
                "thread_id": "thread-123",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "The weather is sunny."
        assert data["tool_used"] == "weather_check"
        assert data["thinking_steps"] == ["tool: weather_check"]
        assert data["took_ms"] == 1234.5

    def test_chat_with_default_thread_id(self, client):
        """测试默认 thread_id。"""
        mock_result = MagicMock()
        mock_result.answer = "ok"
        mock_result.tool_used = None
        mock_result.thinking_steps = []
        mock_result.took_ms = 100.0

        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.chat.return_value = mock_result

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.post("/api/v1/chat", json={"message": "hello"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "ok"

    def test_chat_invalid_json(self, client):
        """测试无效 JSON 请求。"""
        resp = client.post("/api/v1/chat", content="not json", headers={"content-type": "application/json"})
        assert resp.status_code == 422


class TestToolsListEndpoint:
    """GET /api/v1/skills/tools 端点测试。"""

    def test_tools_list_returns_tools(self, client):
        """返回已注册 Tools 列表。"""
        mock_tool = MagicMock()
        mock_tool.name = "weather_check"
        mock_tool.description = "查询天气信息"

        mock_loader = MagicMock()
        mock_loader.registry.tools = {"weather_check": mock_tool}

        mock_agent = MagicMock()
        mock_agent.loader = mock_loader

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.get("/api/v1/skills/tools")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["tools"][0]["name"] == "weather_check"
        assert data["tools"][0]["description"] == "查询天气信息"

    def test_tools_list_empty(self, client):
        """没有 Tools 时返回空列表。"""
        mock_agent = MagicMock()
        mock_agent.loader.registry.tools = {}

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.get("/api/v1/skills/tools")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["tools"] == []

    def test_tools_list_multiple(self, client):
        """多个 Tools 时正确排序和返回。"""
        tools_dict = {
            "code_executor": MagicMock(description="执行代码"),
            "weather_check": MagicMock(description="查询天气"),
            "file_search": MagicMock(description="搜索文件"),
        }

        mock_agent = MagicMock()
        mock_agent.loader.registry.tools = tools_dict

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.get("/api/v1/skills/tools")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        # 应该按名称排序
        names = [t["name"] for t in data["tools"]]
        assert names == sorted(names)


class TestReloadToolsEndpoint:
    """POST /api/v1/skills/tools/reload 端点测试。"""

    def test_reload_success(self, client):
        """成功重新加载。"""
        mock_agent = MagicMock()
        mock_agent.reload.return_value = {
            "status": "ok",
            "loaded": 3,
            "total": 3,
            "time_ms": 123.4,
            "agent_initialized": True,
        }

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.post("/api/v1/skills/tools/reload")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["loaded"] == 3
        assert data["total"] == 3
        assert data["agent_initialized"] is True
        assert isinstance(data["time_ms"], float)

    def test_reload_when_disabled(self, client):
        """Agent 未启用时的重载。"""
        mock_agent = MagicMock()
        mock_agent.reload.return_value = {
            "status": "disabled",
            "loaded": 0,
            "total": 0,
            "time_ms": 0.0,
            "agent_initialized": False,
        }

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            resp = client.post("/api/v1/skills/tools/reload")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disabled"


class TestAgentEndpointIntegration:
    """Agent 端点整体集成测试。"""

    def test_chat_and_tools_consistency(self, client):
        """Tools 列表和 Chat 端点的状态一致性。"""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test"

        mock_result = MagicMock()
        mock_result.answer = "done"
        mock_result.tool_used = "test_tool"
        mock_result.thinking_steps = []
        mock_result.took_ms = 50.0

        mock_loader = MagicMock()
        mock_loader.registry.tools = {"test_tool": mock_tool}

        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.loader = mock_loader
        mock_agent.chat.return_value = mock_result

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            # 先查 tools
            resp_tools = client.get("/api/v1/skills/tools")
            tools_data = resp_tools.json()

            # 再 chat
            resp_chat = client.post("/api/v1/chat", json={"message": "hello"})
            chat_data = resp_chat.json()

        # 状态应该一致
        assert tools_data["total"] == 1
        assert chat_data["answer"] == "done"
        assert mock_agent.chat.called

    def test_reload_then_list(self, client):
        """重载后再查 tools 列表。"""
        reload_result = {
            "status": "ok", "loaded": 2, "total": 2,
            "time_ms": 50.0, "agent_initialized": True,
        }

        tool1 = MagicMock()
        tool1.name = "after_reload"
        tool1.description = "New tool"

        mock_agent = MagicMock()
        mock_agent.reload.return_value = reload_result
        mock_agent.loader.registry.tools = {"after_reload": tool1}

        with patch("api.dependencies._agent_manager_instance", mock_agent):
            # 重载
            resp_reload = client.post("/api/v1/skills/tools/reload")
            assert resp_reload.status_code == 200

            # 查 tools
            resp_tools = client.get("/api/v1/skills/tools")
            tools_data = resp_tools.json()

        assert reload_result["status"] == resp_reload.json()["status"]
        assert tools_data["total"] == 1
        assert tools_data["tools"][0]["name"] == "after_reload"
