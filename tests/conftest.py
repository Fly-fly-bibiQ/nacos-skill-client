"""Conftest — 共享测试 fixtures。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nacos_skill_client.config import Config
from nacos_skill_client.client import NacosSkillClient


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
    from nacos_skill_client.models import SkillItem
    return [
        SkillItem(name="翻译助手", description="翻译文本", enable=True, labels={"category": "nlp"}),
        SkillItem(name="代码生成", description="生成代码", enable=True, labels={"category": "code"}),
        SkillItem(name="天气查询", description="查询天气", enable=True, labels={"category": "search"}),
    ]
