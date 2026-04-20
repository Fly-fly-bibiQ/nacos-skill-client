"""Skill 路由模块。

策略模式 + 工厂模式，支持多种路由策略：
- 基于 LLM 的路由（默认）
- 基于关键词的路由
- 基于规则的路由

典型用法::

    from nacos_skill_client.router import SkillRouter, LLMRouterStrategy
    from openai import OpenAI

    router = SkillRouter(strategy=LLMRouterStrategy(openai_client))
    result = router.route(skills, "帮我翻译一段文本")
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from nacos_skill_client.config import Config
from nacos_skill_client.exceptions import RouterError
from nacos_skill_client.models import RouteResult, SkillItem

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 策略接口
# --------------------------------------------------------------------------- #


class RouterStrategy(ABC):
    """路由策略抽象基类。"""

    @abstractmethod
    def route(self, skills: list[SkillItem], user_query: str) -> RouteResult:
        """路由决策。

        Args:
            skills: 可用 Skill 列表。
            user_query: 用户查询。

        Returns:
            RouteResult 包含推荐的 Skill 名称和理由。
        """
        ...


# --------------------------------------------------------------------------- #
# LLM 路由策略
# --------------------------------------------------------------------------- #


class LLMRouterStrategy(RouterStrategy):
    """基于 LLM 的路由策略。

    将 Skills 简要信息（name + description）+ 用户问题发给 LLM，让 LLM 判断应使用哪个 Skill。
    仅传输 name + description 以节省 token。

    借鉴 skills-agent-proto 的 build_system_prompt() 设计：
    - 只传 SkillMetadata（name + description），不传完整 description
    - 增加正面/负面示例指导 LLM 决策
    - 输出格式更严格（要求 JSON）
    """

    SYSTEM_PROMPT = (
        "你是一个 Skill 路由助手。你的任务是根据用户查询，从可用 Skill 列表中\n"
        "选择最匹配的一个 Skill，或者返回 null 表示不需要任何 Skill。\n"
        "\n"
        "【输出格式要求】\n"
        "- 只返回纯 JSON，不要包含 Markdown 代码块标记（```）\n"
        "- 不要包含反引号、不要包含任何其他文字\n"
        "- JSON 格式必须是: {\"skill_name\": null, \"reason\": \"简要原因\"}\n"
        "- skill_name 必须是可用的 Skill 名称之一，或 null\n"
        "\n"
        "【正面示例 — 需要使用 Skill 的场景】\n"
        "- 需要生成、修改、审查代码 → 使用代码类 Skill\n"
        "- 需要安全审计 → 使用安全审计 Skill\n"
        "- 需要搜索云文档 → 使用文档搜索 Skill\n"
        "- 需要日历/日程管理 → 使用日历 Skill\n"
        "- 需要任务管理 → 使用任务 Skill\n"
        "- 需要浏览器自动化 → 使用浏览器 Skill\n"
        "- 需要文件上传/下载 → 使用文件管理类 Skill\n"
        "- 需要多维表格操作 → 使用多维表格 Skill\n"
        "\n"
        "【负面示例 — 不需要使用 Skill 的场景】\n"
        "- 通用翻译（没有专门的翻译 Skill）→ 返回 null\n"
        "- 简单的聊天、寒暄 → 返回 null\n"
        "- 通用知识问答（天气、常识等，除非有对应 Skill）→ 返回 null\n"
        "- 简单数学计算 → 返回 null\n"
        "- 文本摘要（如果没有专门的摘要 Skill）→ 返回 null\n"
        "- 用户问题与所有 Skill 的描述都不相关 → 返回 null\n"
        "- 通用编程问题但没有代码 Skill → 返回 null\n"
    )

    USER_PROMPT = (
        "可用的 Skill 列表（仅包含 name 和 description）：\n"
        "{skills_list}\n"
        "\n"
        "用户问题：\n"
        "{user_query}\n"
    )

    def __init__(
        self,
        openai_client: OpenAI,
        model: str = "Qwen3.6-35B-A3B-FP8",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> None:
        self.openai_client = openai_client
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def route(self, skills: list[SkillItem], user_query: str) -> RouteResult:
        skills_list_text = self._build_skills_list(skills)
        logger.info("LLM route: %d skills, query=%s (first 50 chars)", len(skills), user_query[:50])
        user_prompt = self.USER_PROMPT.format(skills_list=skills_list_text, user_query=user_query)

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            logger.debug("LLM route: calling model=%s", self._model)
            response = self.openai_client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            text = response.choices[0].message.content
            logger.debug("LLM route: raw response=%s", text[:200])
        except Exception as exc:
            logger.error("LLM route failed (model=%s): %s", self._model, exc, exc_info=True)
            raise RouterError(f"LLM 路由调用失败: {exc}") from exc

        return self._parse_response(text)

    def _build_skills_list(self, skills: list[SkillItem]) -> str:
        if not skills:
            return "（暂无可用 Skill）"
        lines = [f"共 {len(skills)} 个可用 Skill（仅显示 name 和 description）："]
        for i, s in enumerate(skills, 1):
            lines.append(f'  {i}. name: "{s.name}" - description: "{s.description}"')
        return "\n".join(lines)

    @staticmethod
    def _parse_response(text: str) -> RouteResult:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else lines[1] if len(lines) > 1 else ""
            cleaned = cleaned.strip()

        # 尝试标准 JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # LLM 可能返回 Python dict 格式（单引号），尝试替换
            try:
                py_dict = cleaned.replace("'", '"')
                # 处理 None -> null, True -> true, False -> false
                py_dict = re.sub(r'\bNone\b', 'null', py_dict)
                py_dict = re.sub(r'\bTrue\b', 'true', py_dict)
                py_dict = re.sub(r'\bFalse\b', 'false', py_dict)
                data = json.loads(py_dict)
            except json.JSONDecodeError:
                match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group().replace("'", '"'))
                    except json.JSONDecodeError:
                        raise RouterError(f"无法解析 LLM 返回: {text[:200]}")
                else:
                    raise RouterError(f"无法解析 LLM 返回: {text[:200]}")

        skill_name = data.get("skill_name") or data.get("skill")
        reason = data.get("reason", "未提供原因")
        return RouteResult(skill_name=skill_name, reason=reason)


# --------------------------------------------------------------------------- #
# 关键词路由策略（简单匹配）
# --------------------------------------------------------------------------- #


class KeywordRouterStrategy(RouterStrategy):
    """基于关键词匹配的路由策略。

    使用 Skill 的 labels 或 biz_tags 中的关键词进行简单匹配。
    适用于 Skills 不多或关键词明确的场景。
    """

    def route(self, skills: list[SkillItem], user_query: str) -> RouteResult:
        logger.info("Keyword route: %d skills, query=%s", len(skills), user_query[:50])
        best_match: tuple[str, int] | None = None
        query = user_query.lower()
        # 对中文查询，同时按子串匹配
        query_words = [query]  # 整个查询也作为候选
        # 英文用空格拆分，中文用单个字符
        for char in query:
            if char.isascii() and char.isalpha():
                pass  # 已包含在整个查询中
            elif not char.isascii():
                if char not in [c for c in query_words[-1] if c != char if c.isascii() and c.isalpha()]:
                    pass
                query_words.append(char)
        # 去重
        seen = set()
        unique_words: list[str] = []
        for w in query_words:
            if w and w not in seen:
                seen.add(w)
                unique_words.append(w)
        query_words = unique_words

        for skill in skills:
            score = 0
            tags = f"{skill.biz_tags} {skill.name}".lower()
            for word in query_words:
                if word and word in tags:
                    score += len(word)  # 更长匹配得分更高
            if best_match is None or score > best_match[1]:
                best_match = (skill.name, score)

        if best_match and best_match[1] > 0:
            return RouteResult(skill_name=best_match[0], reason=f"关键词匹配得分: {best_match[1]}")
        return RouteResult(skill_name=None, reason="关键词未匹配到任何 Skill")


# --------------------------------------------------------------------------- #
# 工厂类
# --------------------------------------------------------------------------- #


class SkillRouter:
    """Skill 路由器，封装策略模式。

    支持创建 LLM 或关键词路由策略：

    Example::
        router = SkillRouter.create_llm(openai_client)
        router = SkillRouter.create_keyword()
        router = SkillRouter(strategy=my_strategy)
    """

    def __init__(self, strategy: RouterStrategy) -> None:
        self._strategy = strategy

    @classmethod
    def create_llm(
        cls,
        openai_client: OpenAI,
        model: str = "Qwen3.6-35B-A3B-FP8",
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> "SkillRouter":
        """创建基于 LLM 的路由器。"""
        strategy = LLMRouterStrategy(openai_client, model, temperature, max_tokens)
        return cls(strategy=strategy)

    @classmethod
    def create_keyword(cls) -> "SkillRouter":
        """创建基于关键词的路由器。"""
        strategy = KeywordRouterStrategy()
        return cls(strategy=strategy)

    @classmethod
    def from_config(cls, config: Config, openai_client: OpenAI | None = None) -> "SkillRouter":
        """从 Config 创建路由器（默认使用 LLM 路由）。"""
        if openai_client is None:
            from openai import OpenAI
            openai_client = OpenAI(
                base_url=config.llm.base_url,
                api_key=config.llm.api_key,
                timeout=config.llm.timeout,
            )
        strategy = LLMRouterStrategy(
            openai_client,
            temperature=config.router.routing_temperature,
            max_tokens=config.router.routing_max_tokens,
        )
        return cls(strategy=strategy)

    def route(
        self,
        skills: list[SkillItem],
        user_query: str,
    ) -> RouteResult:
        """执行路由决策。"""
        logger.info("SkillRouter.route: strategy=%s, skills=%d, query=%s (first 50 chars)", 
                    type(self._strategy).__name__, len(skills), user_query[:50])
        start = time.time()
        result = self._strategy.route(skills, user_query)
        took_ms = int((time.time() - start) * 1000)
        logger.info("SkillRouter.route: done, skill=%s, reason=%s (%dms)", 
                    result.skill_name or "N/A", result.reason[:80], took_ms)
        return result

    @property
    def strategy(self) -> RouterStrategy:
        return self._strategy


# --------------------------------------------------------------------------- #
# 完整路由 + 执行
# --------------------------------------------------------------------------- #


def _get_instruction_file(
    client: Any,
    skill_name: str,
    priority: list[str] | None = None,
) -> tuple[str, str]:
    """获取 Skill 的指令文件内容。

    Returns:
        (文件名, 内容) 元组。
    """
    if priority is None:
        priority = ["SKILL.md", "AGENTS.md", "SOUL.md"]

    try:
        detail = client.get_skill_detail(skill_name)
    except Exception as exc:
        raise RuntimeError(f"获取 Skill 详情失败: {skill_name}: {exc}") from exc

    if not detail.versions:
        raise RuntimeError(f"Skill 没有可用版本: {skill_name}")

    version = detail.editing_version or (detail.versions[0].version if detail.versions else None)
    if not version:
        raise RuntimeError(f"Skill 没有可用版本: {skill_name}")

    file_map = {
        "SKILL.md": lambda: client.get_skill_md(skill_name, version),
        "AGENTS.md": lambda: client.get_agents_md(skill_name, version),
        "SOUL.md": lambda: client.get_soul_md(skill_name, version),
    }

    for label in priority:
        fetcher = file_map.get(label)
        if fetcher:
            try:
                return (label, fetcher())
            except Exception:
                continue

    available = []
    try:
        vd = client.get_skill_version_detail(skill_name, version)
        available = list(vd.resource.keys())
    except Exception:
        pass
    avail_str = f"（可用资源: {', '.join(available)}）" if available else ""
    raise RuntimeError(f"Skill 没有指令文件: {skill_name}/{version} {avail_str}")


def route_and_execute(
    client: Any,
    router: SkillRouter,
    openai_client: OpenAI,
    user_query: str,
    config: Config | None = None,
) -> dict[str, Any]:
    """完整的路由 + 执行流程。

    Args:
        client: NacosSkillClient 实例。
        router: SkillRouter 实例。
        openai_client: OpenAI 客户端。
        user_query: 用户查询。
        config: 配置（用于优先级等）。

    Returns:
        包含 query、route、skill_md、answer、took_ms 的字典。
    """
    start = time.time()

    skills = client.get_all_skills()[: (config.router.max_skills_for_routing if config else 100)]
    route_result = router.route(skills, user_query)

    answer: str
    skill_md: str | None = None

    if route_result.skill_name:
        try:
            file_label, skill_md = _get_instruction_file(client, route_result.skill_name)
            prompt = (
                f"下面的内容是 {route_result.skill_name} 的指令文件（{file_label}），"
                f"请按照以上指令，帮助用户解决问题。\n\n"
                f"--- 指令开始 ---\n{skill_md}\n--- 指令结束 ---\n\n"
                f"用户问题：\n{user_query}\n"
            )
            messages = [
                {"role": "system", "content": "你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。"},
                {"role": "user", "content": prompt},
            ]
            resp = openai_client.chat.completions.create(
                model=config.llm.model if config else "Qwen3.6-35B-A3B-FP8",
                messages=messages,
                temperature=config.llm.temperature if config else 0.1,
                max_tokens=config.llm.max_tokens if config else 4096,
            )
            answer = resp.choices[0].message.content
        except Exception as exc:
            answer = f"⚠️ 获取 Skill 内容失败: {exc}"
    else:
        resp = openai_client.chat.completions.create(
            model=config.llm.model if config else "default",
            messages=[{"role": "user", "content": user_query}],
            temperature=config.llm.temperature if config else 0.1,
            max_tokens=config.llm.max_tokens if config else 4096,
        )
        answer = resp.choices[0].message.content

    took_ms = int((time.time() - start) * 1000)
    return {
        "query": user_query,
        "route": route_result.to_dict(),
        "skill_md": skill_md,
        "answer": answer,
        "took_ms": took_ms,
    }
