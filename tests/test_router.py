"""测试路由模块。"""

import json
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


class TestLLMRouterStrategyPrompt:
    """测试 LLM 路由策略的 prompt 设计。"""

    def test_system_prompt_includes_examples(self):
        """SYSTEM_PROMPT 应包含正面/负面示例。"""
        strategy = LLMRouterStrategy(MagicMock())
        assert "正面示例" in strategy.SYSTEM_PROMPT
        assert "负面示例" in strategy.SYSTEM_PROMPT

    def test_system_prompt_requires_json(self):
        """SYSTEM_PROMPT 应要求纯 JSON 输出。"""
        strategy = LLMRouterStrategy(MagicMock())
        assert "只返回纯 JSON" in strategy.SYSTEM_PROMPT
        assert "不要包含 Markdown 代码块标记" in strategy.SYSTEM_PROMPT

    def test_user_prompt_has_skills_and_query(self):
        """USER_PROMPT 应包含 skills_list 和 user_query 模板。"""
        strategy = LLMRouterStrategy(MagicMock())
        assert "{skills_list}" in strategy.USER_PROMPT
        assert "{user_query}" in strategy.USER_PROMPT

    def test_routing_prompt_replaced_by_separate_prompts(self):
        """旧的 ROUTING_PROMPT 不应存在。"""
        strategy = LLMRouterStrategy(MagicMock())
        assert not hasattr(strategy, 'ROUTING_PROMPT')

    def test_parse_response_standard_json(self):
        """测试解析标准 JSON。"""
        result = LLMRouterStrategy._parse_response('{"skill_name": "翻译助手", "reason": "匹配翻译"}')
        assert result.skill_name == "翻译助手"
        assert result.reason == "匹配翻译"

    def test_parse_response_null_skill(self):
        """测试解析 null skill。"""
        result = LLMRouterStrategy._parse_response('{"skill_name": null, "reason": "不需要 Skill"}')
        assert result.skill_name is None
        assert result.reason == "不需要 Skill"

    def test_parse_response_with_markdown_block(self):
        """测试解析带 Markdown 代码块的响应。"""
        text = '''```json
{"skill_name": "代码生成", "reason": "需要代码"}
```'''
        result = LLMRouterStrategy._parse_response(text)
        assert result.skill_name == "代码生成"
        assert result.reason == "需要代码"

    def test_parse_response_python_dict(self):
        """测试解析 Python dict 格式（单引号、None）。"""
        text = "{'skill_name': '翻译助手', 'reason': '匹配翻译'}"
        result = LLMRouterStrategy._parse_response(text)
        assert result.skill_name == "翻译助手"

    def test_parse_response_python_null(self):
        """测试解析 Python dict 格式的 null。"""
        text = "{'skill_name': None, 'reason': '不需要'}"
        result = LLMRouterStrategy._parse_response(text)
        assert result.skill_name is None

    def test_build_skills_list_empty(self):
        """测试空 skill 列表。"""
        strategy = LLMRouterStrategy(MagicMock())
        text = strategy._build_skills_list([])
        assert "暂无可用 Skill" in text

    def test_build_skills_list_non_empty(self):
        """测试非空 skill 列表。"""
        strategy = LLMRouterStrategy(MagicMock())
        skills = [
            SkillItem(name="翻译", description="翻译文本"),
            SkillItem(name="代码", description="生成代码"),
        ]
        text = strategy._build_skills_list(skills)
        assert "共 2 个可用 Skill" in text
        assert '"翻译"' in text
        assert '"代码"' in text
