"""LangGraph Agent — 流式 Skill 路由执行。

基于 LangGraph StateGraph 构建 Skill 路由 Agent 图：

Graph 流程:
  START → discover → route → (activate | execute_direct) → END

每个节点:
  - discover: 从 Nacos 发现可用 Skills（元数据）
  - route: LLM 路由决策，选择最匹配的 Skill
  - activate: 加载 Skill 的指令文件
  - execute: 使用 Skill 指令 + 用户问题调用 LLM 流式输出
  - execute_direct: 无 Skill 时直接 LLM 调用

SSE 事件流:
  discovered → skill_selected / no_skill → instruction_loaded → content* → done

使用方式 (FastAPI SSE):
    from agent.stream import stream_agent_response

    def endpoint():
        for event in stream_agent_response(user_msg, client, config, llm, router):
            yield event
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


def stream_agent_response(
    user_message: str,
    client: Any,
    config: Any,
    llm: Any,
    router: Any,
) -> Iterator[dict[str, Any]]:
    """Agent 流式响应生成器。

    将 LangGraph 的节点流程映射为 SSE 事件，供 FastAPI EventSourceResponse 使用。

    Args:
        user_message: 用户输入消息
        client: NacosSkillClient 实例
        config: Config 实例
        llm: LangChain ChatModel (stream 接口)
        router: SkillRouter 实例

    Yields:
        {"event": str, "data": str} SSE 事件
    """
    # ── Step 1: Discover Skills ──
    items = client.get_all_skills()[: config.router.max_skills_for_routing]
    skills = [{"name": s.name, "description": s.description or ""} for s in items]
    logger.info("stream: discovered %d skills", len(skills))
    yield {"event": "discovered", "data": json.dumps({"count": len(skills), "skills": skills}, ensure_ascii=False)}

    # ── Step 2: Route ──
    result = router.route(skills, user_message)
    logger.info("stream: route skill=%s, reason=%s", result.skill_name or "N/A", result.reason[:80])

    if result.skill_name:
        # ── Step 3: Activate ──
        yield {"event": "skill_selected", "data": json.dumps({
            "skill_name": result.skill_name,
            "reason": result.reason,
        }, ensure_ascii=False)}

        priority = config.router.instruction_file_priority
        file_label, instruction = "", ""

        # 缓存优先
        if client.cache and client.cache.has_skill(result.skill_name):
            file_label, instruction = client.cache.get_skill_file(
                result.skill_name, priority[0],
            )

        # Nacos 下载
        if not instruction:
            file_label, instruction = client.get_instruction_file(
                result.skill_name, "", priority=priority,
            )

        # 截断过长指令
        max_len = 8000
        if len(instruction) > max_len:
            instruction = instruction[:max_len] + f"\n\n...(truncated, total {len(instruction)} chars)"

        logger.info("stream: instruction loaded (%s, %d chars)", file_label, len(instruction))
        yield {"event": "instruction_loaded", "data": json.dumps({
            "file": file_label,
            "length": len(instruction),
            "skill_name": result.skill_name,
        }, ensure_ascii=False)}

        # ── Step 4: Execute with Skill ──
        system_msg = SystemMessage(
            content="你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。",
        )
        user_content = (
            f"--- Skill: {result.skill_name} ({file_label}) ---\n"
            f"{instruction}\n--- 指令结束 ---\n\n"
            f"用户问题：\n{user_message}\n"
        )
        messages = [system_msg, HumanMessage(content=user_content)]

        resp = llm.stream(
            messages,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
        for chunk in resp:
            if chunk.content:
                yield {"event": "content", "data": chunk.content}
    else:
        # ── Step 3 (bypass): Direct LLM ──
        logger.info("stream: no skill matched, direct LLM call")
        yield {"event": "no_skill", "data": json.dumps({
            "reason": result.reason,
        }, ensure_ascii=False)}

        resp = llm.stream(
            [HumanMessage(content=user_message)],
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
        for chunk in resp:
            if chunk.content:
                yield {"event": "content", "data": chunk.content}

    # ── Done ──
    yield {"event": "done", "data": json.dumps({"status": "complete"})}
