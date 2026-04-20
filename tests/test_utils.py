"""测试工具函数。"""

import pytest
from unittest.mock import MagicMock, patch

from nacos_skill_client.utils import create_llm_client, call_llm, build_prompt


class TestCreateLLMClient:
    def test_creates_client(self):
        client = create_llm_client("http://test:8000/v1", "test-key", 60)
        assert client.base_url == "http://test:8000/v1/"
        assert client.api_key == "test-key"


class TestBuildPrompt:
    def test_builds_messages(self):
        msgs = build_prompt("You are helpful", "Hello")
        assert len(msgs) == 2
        assert msgs[0] == {"role": "system", "content": "You are helpful"}
        assert msgs[1] == {"role": "user", "content": "Hello"}


class TestCallLLM:
    def test_non_streaming(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="Hello world"))]
        mock_client.chat.completions.create.return_value = mock_resp

        result = call_llm(mock_client, [{"role": "user", "content": "hi"}], model="test-model")
        assert result == "Hello world"

    def test_streaming(self):
        mock_client = MagicMock()
        gen = call_llm(mock_client, [{"role": "user", "content": "hi"}], stream=True)
        # Should return a generator (not a function)
        assert hasattr(gen, "__iter__")
