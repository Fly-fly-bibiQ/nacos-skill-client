"""测试数据模型。"""

import pytest
from pathlib import Path
from nacos_skill_client.models import (
    SkillContent,
    SkillDetail,
    SkillItem,
    SkillListResult,
    SkillMetadata,
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


class TestSkillMetadata:
    """测试 SkillMetadata 数据类（Level 1 轻量级发现）。"""

    def test_basic(self):
        m = SkillMetadata(
            name="翻译助手",
            description="翻译文本",
            skill_path=Path("/tmp/test-skill"),
        )
        assert m.name == "翻译助手"
        assert m.description == "翻译文本"
        assert m.skill_path == Path("/tmp/test-skill")

    def test_to_prompt_line(self):
        m = SkillMetadata(name="code-gen", description="生成代码", skill_path=Path("/tmp"))
        assert m.to_prompt_line() == "- **code-gen**: 生成代码"


class TestSkillContent:
    """测试 SkillContent 数据类（Level 2 按需加载）。"""

    def test_basic(self):
        metadata = SkillMetadata(name="test", description="desc", skill_path=Path("/tmp"))
        content = SkillContent(metadata=metadata, instructions="# Hello\n\nRun script")
        assert content.metadata.name == "test"
        assert content.instructions == "# Hello\n\nRun script"


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
