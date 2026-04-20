"""测试 SkillCache 缓存模块。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nacos_skill_client.cache import SkillCache
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config, CacheConfig


class TestSkillCache:
    """SkillCache 单元测试。"""

    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """临时缓存目录 fixture。"""
        return str(tmp_path / "test_skill_cache")

    def test_init_creates_dir(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        assert Path(temp_cache_dir).is_dir()

    def test_has_skill_returns_false_when_not_cached(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        assert cache.has_skill("翻译助手") is False

    def test_has_skill_returns_true_after_save(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        content = "# 翻译助手\n\n## 描述\n翻译所有文本"
        cache.save_skill("翻译助手", content, "AGENTS.md")
        assert cache.has_skill("翻译助手") is True

    def test_save_and_get_file(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        content = "# AGENTS 指令\n\n你是一名翻译专家。"
        cache.save_skill("代码生成", content, "AGENTS.md")

        label, retrieved = cache.get_skill_file("代码生成", "AGENTS.md")
        assert label == "AGENTS.md"
        assert retrieved == content

    def test_get_skill_file_returns_none_for_missing(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        label, retrieved = cache.get_skill_file("不存在", "AGENTS.md")
        assert label is None
        assert retrieved is None

    def test_get_skill_file_returns_none_for_missing_filename(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("翻译助手", "content", "AGENTS.md")
        label, retrieved = cache.get_skill_file("翻译助手", "SOUL.md")
        assert label is None
        assert retrieved is None

    def test_save_multiple_files(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("翻译助手", "AGENTS 内容", "AGENTS.md")
        cache.save_skill("翻译助手", "SOUL 内容", "SOUL.md")

        assert cache.has_skill("翻译助手") is True
        _, agents = cache.get_skill_file("翻译助手", "AGENTS.md")
        _, soul = cache.get_skill_file("翻译助手", "SOUL.md")
        assert agents == "AGENTS 内容"
        assert soul == "SOUL 内容"

    def test_get_skill_manifest(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("天气查询", "天气内容", "AGENTS.md", version="v1.0", description="查询天气")

        manifest = cache.get_skill_manifest("天气查询")
        assert manifest is not None
        assert manifest["name"] == "天气查询"
        assert manifest["version"] == "v1.0"
        assert manifest["description"] == "查询天气"
        assert "download_time" in manifest

    def test_get_skill_manifest_returns_none_for_missing(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        assert cache.get_skill_manifest("不存在") is None

    def test_get_all_cached_skills(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("翻译助手", "内容1", "AGENTS.md")
        cache.save_skill("代码生成", "内容2", "AGENTS.md")

        skills = cache.get_all_cached_skills()
        assert "翻译助手" in skills
        assert "代码生成" in skills
        assert len(skills) == 2

    def test_get_all_cached_skills_empty(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        skills = cache.get_all_cached_skills()
        assert skills == []

    def test_safe_filename_handles_chinese(self, temp_cache_dir):
        """中文名称应转为安全的文件名。"""
        cache = SkillCache(cache_dir=temp_cache_dir)
        # 中文名称会被转为带下划线的安全文件名
        cache.save_skill("ZK管家", "内容", "AGENTS.md")
        assert cache.has_skill("ZK管家") is True
        _, content = cache.get_skill_file("ZK管家", "AGENTS.md")
        assert content == "内容"

    def test_manifest_download_time_is_current(self, temp_cache_dir):
        before = int(time.time() * 1000)
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("测试技能", "内容", "AGENTS.md")
        after = int(time.time() * 1000)

        manifest = cache.get_skill_manifest("测试技能")
        assert before <= manifest["download_time"] <= after

    def test_consecutive_saves_update_manifest(self, temp_cache_dir):
        cache = SkillCache(cache_dir=temp_cache_dir)
        cache.save_skill("技能A", "内容1", "AGENTS.md", version="v1.0")
        time.sleep(0.01)
        cache.save_skill("技能A", "内容2", "AGENTS.md", version="v2.0")

        manifest = cache.get_skill_manifest("技能A")
        assert manifest["version"] == "v2.0"
        assert manifest["description"] == ""  # 第二次保存未传 description


class TestSkillCacheWithClient:
    """SkillCache 与 NacosSkillClient 集成测试（mock）。"""

    @pytest.fixture
    def mock_client_no_cache(self, config):
        """不带缓存的客户端（mock Nacos API）。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(config=config, cache=None)
            yield client

    @pytest.fixture
    def mock_client_with_cache(self, config, tmp_path):
        """带缓存的客户端（mock Nacos API）。"""
        cache = SkillCache(cache_dir=str(tmp_path / "cache"))
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(config=config, cache=cache)
            yield client

    def test_get_skill_md_cache_miss_then_download(self, mock_client_with_cache, tmp_path):
        """缓存未命中时，get_skill_md 从 Nacos 获取。"""
        # 验证缓存为空
        assert not mock_client_with_cache.cache.has_skill("翻译助手")

        # mock get_instruction_file 返回内容
        with patch.object(
            mock_client_with_cache,
            'get_instruction_file',
            return_value=("AGENTS.md", "# 翻译助手\n\n翻译所有文本。"),
        ):
            result = mock_client_with_cache.get_skill_md("翻译助手", use_cache=True)

        assert result is not None
        assert "翻译所有文本" in result["content"]

    def test_get_skill_md_cache_hit(self, mock_client_with_cache, tmp_path):
        """缓存命中时，直接从缓存读取。"""
        # 先手动缓存
        mock_client_with_cache.cache.save_skill(
            "天气查询",
            "# 天气查询\n\n查询天气信息。",
            "AGENTS.md",
        )
        assert mock_client_with_cache.cache.has_skill("天气查询")

        # get_skill_md 应从缓存读取，不会调用 Nacos
        with patch.object(
            mock_client_with_cache,
            'get_instruction_file',
            side_effect=RuntimeError("不应调用 Nacos"),
        ):
            result = mock_client_with_cache.get_skill_md("天气查询", use_cache=True)

        assert result is not None
        assert "查询天气信息" in result["content"]

    def test_get_skill_md_cache_disabled(self, mock_client_with_cache, tmp_path):
        """缓存禁用时，即使有缓存也不使用。"""
        # 先缓存
        mock_client_with_cache.cache.save_skill(
            "代码生成",
            "# 代码生成\n\n生成代码。",
            "AGENTS.md",
        )

        # 使用 use_cache=False 应从 Nacos 获取
        with patch.object(
            mock_client_with_cache,
            'get_instruction_file',
            return_value=("AGENTS.md", "# 代码生成\n\n生成各种代码。"),
        ) as mock_get:
            result = mock_client_with_cache.get_skill_md("代码生成", use_cache=False)

        assert result is not None
        assert "生成各种代码" in result["content"]
        mock_get.assert_called_once()

    def test_download_and_cache_skill_no_cache(self, mock_client_no_cache):
        """没有缓存时，download_and_cache_skill 返回空列表。"""
        with patch.object(
            mock_client_no_cache,
            'get_skill_version_detail',
            return_value=MagicMock(
                name="测试技能",
                description="测试",
                resource={
                    "config_AGENTS__md": "# 测试\n\n这是一项测试技能。",
                    "config_SOUL__md": "# SOUL\n\n测试灵魂。",
                },
            ),
        ):
            saved = mock_client_no_cache.download_and_cache_skill("测试技能")
        assert saved == []

    def test_download_and_cache_skill_with_cache(self, mock_client_with_cache):
        """有缓存时，download_and_cache_skill 保存文件。"""
        with patch.object(
            mock_client_with_cache,
            'get_skill_version_detail',
            return_value=MagicMock(
                name="测试技能",
                description="测试描述",
                resource={
                    "config_AGENTS__md": "# 测试\n\n这是一项测试技能。",
                    "config_SOUL__md": "# SOUL\n\n测试灵魂。",
                },
            ),
        ):
            saved = mock_client_with_cache.download_and_cache_skill("测试技能")

        assert "AGENTS.md" in saved
        assert "SOUL.md" in saved

        # 验证缓存
        assert mock_client_with_cache.cache.has_skill("测试技能")
        _, agents = mock_client_with_cache.cache.get_skill_file("测试技能", "AGENTS.md")
        assert "测试技能" in agents
        manifest = mock_client_with_cache.cache.get_skill_manifest("测试技能")
        assert manifest is not None
        assert manifest["description"] == "测试描述"


class TestCacheConfig:
    """CacheConfig 单元测试。"""

    def test_default_values(self):
        cfg = CacheConfig()
        assert cfg.enabled is True
        assert cfg.dir == ".skill_cache"
        assert cfg.ttl_days == 7

    def test_custom_values(self):
        cfg = CacheConfig(enabled=False, dir="/tmp/skill_cache", ttl_days=30)
        assert cfg.enabled is False
        assert cfg.dir == "/tmp/skill_cache"
        assert cfg.ttl_days == 30

    def test_ttl_out_of_range(self):
        with pytest.raises(Exception):  # Pydantic validation error
            CacheConfig(ttl_days=0)


class TestConfigIntegration:
    """配置缓存集成测试。"""

    def test_config_load_cache(self, tmp_path):
        yaml_content = """
cache:
  enabled: true
  dir: /tmp/test_cache
  ttl_days: 14
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        cfg = Config.from_yaml(yaml_file)
        assert cfg.cache.enabled is True
        assert cfg.cache.dir == "/tmp/test_cache"
        assert cfg.cache.ttl_days == 14

    def test_config_default_cache(self):
        cfg = Config()
        assert cfg.cache.enabled is True
        assert cfg.cache.dir == ".skill_cache"
        assert cfg.cache.ttl_days == 7
