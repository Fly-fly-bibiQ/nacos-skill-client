"""测试数据模型。"""

import pytest
from nacos_skill_client.models import (
    SkillItem,
    SkillDetail,
    SkillListResult,
    SkillVersionInfo,
    SkillVersionDetail,
    SkillResourceFile,
    RouteResult,
)


class TestSkillItem:
    def test_from_dict(self):
        raw = {
            "namespaceId": "public",
            "name": "test-skill",
            "description": "A test skill",
            "updateTime": 1700000000000,
            "enable": True,
            "labels": {"category": "nlp"},
            "editingVersion": "v1",
            "update_time": 1700000000000,
        }
        item = SkillItem(**raw)
        assert item.name == "test-skill"
        assert item.labels == {"category": "nlp"}
        assert item.editing_version == "v1"
        assert item.update_time_dt is not None

    def test_empty_dict(self):
        item = SkillItem()
        assert item.name == ""
        assert item.labels == {}


class TestSkillDetail:
    def test_from_dict_with_versions(self):
        raw = {
            "namespaceId": "public",
            "name": "test-skill",
            "description": "Test",
            "versions": [
                {"version": "v1", "status": "online", "author": "dev1", "description": "First version"},
            ],
        }
        detail = SkillDetail(**raw)
        assert detail.name == "test-skill"
        assert len(detail.versions) == 1
        assert detail.versions[0].version == "v1"


class TestSkillListResult:
    def test_from_dict(self):
        raw = {
            "totalCount": 10,
            "pageNumber": 1,
            "pagesAvailable": 1,
            "pageItems": [
                {"namespaceId": "public", "name": "skill1", "description": "S1", "update_time": 0},
            ],
        }
        result = SkillListResult(**raw)
        assert result.total_count == 10
        assert len(result.page_items) == 1
        assert result.page_items[0].name == "skill1"


class TestRouteResult:
    def test_to_dict(self):
        r = RouteResult(skill_name="test-skill", reason="matches intent")
        assert r.to_dict() == {"skill_name": "test-skill", "reason": "matches intent"}

    def test_null_skill(self):
        r = RouteResult(skill_name=None, reason="no skill needed")
        assert r.to_dict() == {"skill_name": None, "reason": "no skill needed"}


class TestSkillResourceFile:
    def test_basic(self):
        f = SkillResourceFile(file_name="SKILL.md", content="# Test")
        assert f.file_name == "SKILL.md"
        assert f.content == "# Test"


class TestSkillVersionDetail:
    def test_from_dict_with_resource(self):
        raw = {
            "name": "test-skill",
            "namespaceId": "public",
            "description": "Test",
            "content": '{"key": "value"}',
            "resource": {
                "config_SKILL__md": "# SKILL content",
                "config_AGENTS__md": "# AGENTS content",
            },
        }
        detail = SkillVersionDetail(**raw)
        assert detail.name == "test-skill"
        assert "config_SKILL__md" in detail.resource
        assert detail.resource["config_SKILL__md"].content == "# SKILL content"
