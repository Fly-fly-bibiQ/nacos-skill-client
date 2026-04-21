"""Conftest — 共享测试 fixtures。"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config
from nacos_skill_client.models import SkillItem


@pytest.fixture
def config():
    """测试用配置。"""
    cfg = Config(
        nacos={
            "server_addr": "http://test-nacos:8002",
            "api_addr": "http://test-nacos:8848",
            "username": "test",
            "password": "test",
            "namespace_id": "test-ns",
        },
    )
    return cfg


@pytest.fixture
def mock_skill_items():
    """模拟 Skill 列表项。"""
    return [
        SkillItem(name="翻译助手", description="翻译文本", enable=True, labels={"category": "nlp"}),
        SkillItem(name="代码生成", description="生成代码", enable=True, labels={"category": "code"}),
        SkillItem(name="天气查询", description="查询天气", enable=True, labels={"category": "search"}),
    ]


# --------------------------------------------------------------------------- #
#  TestClient fixture（替代 test_routes.py 中的本地 fixture）
# --------------------------------------------------------------------------- #

@pytest.fixture
def client():
    """TestClient fixture（供 routes/agent 测试使用）."""
    return TestClient(app)
