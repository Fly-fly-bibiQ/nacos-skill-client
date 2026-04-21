"""Tests for Phase 4 features: SSE streaming, CLI module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


class TestSSEStreamEndpoint:
    """GET /api/v1/chat/stream 端点测试。"""

    def _patch_agent(self, mock_agent):
        return patch("api.dependencies._agent_manager_instance", mock_agent)

    def test_stream_disabled(self, client):
        mock_agent = MagicMock()
        mock_agent.enabled = False
        with self._patch_agent(mock_agent):
            resp = client.get(
                "/api/v1/chat/stream",
                params={"message": "hello", "thread_id": "t1"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        content = resp.content.decode("utf-8")
        assert "event: error" in content
        assert "Agent disabled" in content

    def test_stream_success(self, client):
        mock_result = MagicMock()
        mock_result.answer = "北京今天晴"
        mock_result.tool_used = "weather_check"
        mock_result.thinking_steps = ["analyzed intent", "called weather_check"]
        mock_result.took_ms = 1234.5
        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.chat.return_value = mock_result
        with self._patch_agent(mock_agent):
            resp = client.get(
                "/api/v1/chat/stream",
                params={"message": "北京天气", "thread_id": "t1"},
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        content = resp.content.decode("utf-8")
        for evt in ["event: text", "event: tool_used", "event: thinking_steps", "event: took_ms", "event: done"]:
            assert evt in content
        assert "北京今天晴" in content

    def test_stream_without_tool(self, client):
        mock_result = MagicMock()
        mock_result.answer = "这是一个直接回答"
        mock_result.tool_used = None
        mock_result.thinking_steps = ["completed"]
        mock_result.took_ms = 100.0
        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.chat.return_value = mock_result
        with self._patch_agent(mock_agent):
            resp = client.get(
                "/api/v1/chat/stream",
                params={"message": "你好", "thread_id": "t1"},
            )
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "event: text" in content
        assert "event: done" in content
        assert "event: tool_used" not in content

    def test_stream_headers(self, client):
        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.chat.return_value = MagicMock(
            answer="ok", tool_used=None, thinking_steps=[], took_ms=0.0,
        )
        with self._patch_agent(mock_agent):
            resp = client.get(
                "/api/v1/chat/stream",
                params={"message": "hello", "thread_id": "t1"},
            )
        assert "no-cache" in resp.headers.get("cache-control", "").lower()
        assert "keep-alive" in resp.headers.get("connection", "").lower()

    def test_stream_empty_message(self, client):
        mock_agent = MagicMock()
        mock_agent.enabled = True
        with self._patch_agent(mock_agent):
            resp = client.get(
                "/api/v1/chat/stream",
                params={"message": "", "thread_id": "t1"},
            )
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "event: error" in content
        assert "message is required" in content


class TestCLIModule:
    """CLI 模块基本功能测试。"""

    def test_cli_class_import(self):
        from nacos_skill_client.agent.cli import NacosAgentCLI
        assert NacosAgentCLI is not None

    def test_cli_init(self):
        from nacos_skill_client.agent.cli import NacosAgentCLI
        cli = NacosAgentCLI()
        assert cli.api_url == "http://127.0.0.1:8002"
        assert cli.timeout == 120
        assert cli.message_count == 0
        assert cli.thread_id == "cli-session"

    def test_cli_custom_config(self):
        from nacos_skill_client.agent.cli import NacosAgentCLI
        cli = NacosAgentCLI(api_url="http://custom:9002", timeout=60)
        assert cli.api_url == "http://custom:9002"
        assert cli.timeout == 60

    def test_cli_has_help_text(self):
        from nacos_skill_client.agent.cli import NacosAgentCLI
        cli = NacosAgentCLI()
        assert "/quit" in cli.HELP_TEXT
        assert "/clear" in cli.HELP_TEXT
        assert "/tools" in cli.HELP_TEXT
        assert "/reload" in cli.HELP_TEXT

    def test_main_function_exists(self):
        from nacos_skill_client.agent.cli import main
        assert callable(main)

    def test_sse_helper_functions(self):
        from api.routes import _sse_event, _format_sse
        event = _sse_event("text", {"content": "hello"})
        assert event["event"] == "text"
        assert event["data"] == {"content": "hello"}
        formatted = _format_sse(event)
        assert "event: text" in formatted
        assert '"content": "hello"' in formatted


class TestPhase4Integration:
    """Phase 4 功能集成测试。"""

    def _patch_agent(self, mock_agent):
        return patch("api.dependencies._agent_manager_instance", mock_agent)

    def test_stream_then_tools_consistency(self, client):
        mock_tool = MagicMock()
        mock_tool.name = "scan_tool"
        mock_tool.description = "Scan"
        mock_result = MagicMock()
        mock_result.answer = "ok"
        mock_result.tool_used = "scan_tool"
        mock_result.thinking_steps = []
        mock_result.took_ms = 100.0
        mock_loader = MagicMock()
        mock_loader.registry.tools = {"scan_tool": mock_tool}
        mock_agent = MagicMock()
        mock_agent.enabled = True
        mock_agent.loader = mock_loader
        mock_agent.chat.return_value = mock_result
        with self._patch_agent(mock_agent):
            resp_stream = client.get(
                "/api/v1/chat/stream",
                params={"message": "hello", "thread_id": "t1"},
            )
            stream_content = resp_stream.content.decode("utf-8")
            resp_tools = client.get("/api/v1/skills/tools")
            tools_data = resp_tools.json()
        assert "scan_tool" in stream_content
        assert tools_data["total"] == 1
        assert tools_data["tools"][0]["name"] == "scan_tool"

    def test_reload_then_list(self, client):
        mock_agent = MagicMock()
        mock_agent.reload.return_value = {
            "status": "ok", "loaded": 2, "total": 2,
            "time_ms": 50.0, "agent_initialized": True,
        }
        tool1 = MagicMock()
        tool1.name = "after_reload"
        tool1.description = "New tool"
        mock_agent.loader.registry.tools = {"after_reload": tool1}
        with self._patch_agent(mock_agent):
            resp_reload = client.post("/api/v1/skills/tools/reload")
            assert resp_reload.status_code == 200
            reload_data = resp_reload.json()
            assert reload_data["status"] == "ok"
            resp_tools = client.get("/api/v1/skills/tools")
            tools_data = resp_tools.json()
        assert tools_data["total"] == 1
        assert tools_data["tools"][0]["name"] == "after_reload"
