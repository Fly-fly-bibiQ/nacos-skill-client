"""测试配置模型。"""

import pytest
from pydantic import ValidationError

from nacos_skill_client.config import Config, NacosConfig, LLMConfig, RouterConfig


class TestNacosConfig:
    def test_default_values(self):
        cfg = NacosConfig()
        assert cfg.server_addr == "http://192.168.1.118:8002"
        assert cfg.username == "nacos"
        assert cfg.namespace_id == "public"
        assert cfg.timeout == 30
        assert cfg.verify_ssl is True

    def test_custom_values(self):
        cfg = NacosConfig(
            server_addr="http://test:8848",
            username="admin",
            password="secret",
            timeout=60,
        )
        assert cfg.server_addr == "http://test:8848"
        assert cfg.username == "admin"
        assert cfg.timeout == 60


class TestLLMConfig:
    def test_default_values(self):
        cfg = LLMConfig()
        assert cfg.base_url == "http://192.168.1.118:8000/v1"
        assert cfg.model == "Qwen3.6-35B-A3B-FP8"
        assert cfg.api_key == "dummy"
        assert cfg.temperature == 0.1

    def test_invalid_temperature(self):
        with pytest.raises(ValidationError):
            LLMConfig(temperature=3.0)


class TestRouterConfig:
    def test_defaults(self):
        cfg = RouterConfig()
        assert cfg.max_skills_for_routing == 100
        assert cfg.instruction_file_priority == ["SKILL.md", "AGENTS.md", "SOUL.md"]


class TestConfigFromYAML:
    def test_from_yaml_with_custom_values(self, tmp_path):
        yaml_content = """
nacos:
  server_addr: http://test:9999
  username: testuser
  password: testpass
llm:
  base_url: http://test:8001/v1
  model: test-model
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        cfg = Config.from_yaml(yaml_file)
        assert cfg.nacos.server_addr == "http://test:9999"
        assert cfg.nacos.username == "testuser"
        assert cfg.llm.base_url == "http://test:8001/v1"
        assert cfg.llm.model == "test-model"

    def test_from_yaml_missing_file(self):
        cfg = Config.from_yaml("/nonexistent/config.yaml")
        assert cfg.nacos.server_addr == "http://192.168.1.118:8002"

    def test_programmatic_override(self):
        # 验证通过程序化方式可以覆盖配置
        cfg = Config(
            nacos={"server_addr": "http://env:1234"},
            llm={"model": "env-model"},
        )
        assert cfg.nacos.server_addr == "http://env:1234"
        assert cfg.llm.model == "env-model"


class TestConfigAPI:
    def test_get_api_addr(self):
        cfg = Config(nacos=NacosConfig(server_addr="http://a:8002", api_addr="http://b:8848"))
        assert cfg.get_api_addr() == "http://b:8848"

    def test_get_api_addr_fallback(self):
        cfg = Config(nacos=NacosConfig(server_addr="http://a:8002"))
        assert cfg.get_api_addr() == "http://a:8002"
