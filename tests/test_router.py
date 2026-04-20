"""测试路由模块。"""

import pytest
from unittest.mock import MagicMock, patch

from nacos_skill_client.models import SkillItem, RouteResult
from nacos_skill_client.router import (
    KeywordRouterStrategy,
    LLMRouterStrategy,
    SkillRouter,
)


class TestKeywordRouterStrategy:
    def test_match_by_tags(self):
        strategy = KeywordRouterStrategy()
        skills = [
            SkillItem(name="翻译助手", description="翻译文本", biz_tags="translate translation"),
            SkillItem(name="代码生成", description="生成代码", biz_tags="code programming"),
        ]
        result = strategy.route(skills, "帮我翻译这段文字")
        assert result.skill_name == "翻译助手"
        assert "翻译" in result.reason or "关键词" in result.reason

    def test_no_match(self):
        strategy = KeywordRouterStrategy()
        skills = [
            SkillItem(name="代码生成", description="生成代码", biz_tags="code"),
        ]
        result = strategy.route(skills, "今天天气怎么样")
        assert result.skill_name is None

    def test_empty_skills(self):
        strategy = KeywordRouterStrategy()
        result = strategy.route([], "任何查询")
        assert result.skill_name is None


class TestSkillRouterFactory:
    def test_create_llm(self):
        mock_client = MagicMock()
        router = SkillRouter.create_llm(mock_client)
        assert isinstance(router.strategy, LLMRouterStrategy)

    def test_create_keyword(self):
        router = SkillRouter.create_keyword()
        assert isinstance(router.strategy, KeywordRouterStrategy)

    def test_from_config(self):
        from nacos_skill_client.config import Config
        config = Config()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"skill_name": "test", "reason": "test"}'))]
        )
        router = SkillRouter.from_config(config, mock_client)
        assert isinstance(router.strategy, LLMRouterStrategy)

    def test_route_delegates_to_strategy(self):
        mock_strategy = MagicMock()
        mock_strategy.route.return_value = RouteResult(skill_name="mock-skill", reason="test")
        router = SkillRouter(strategy=mock_strategy)
        result = router.route([], "test query")
        assert result.skill_name == "mock-skill"
        mock_strategy.route.assert_called_once()
