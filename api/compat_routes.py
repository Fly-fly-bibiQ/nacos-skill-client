"""兼容 skills-agent-proto 的适配器路由。

把我们的 /api/v1/* API 包装成 skills-agent-proto 期望的 /api/* 接口，
让 web 前端零改动即可对接。

接口映射:
  /api/skills           → 获取所有 Skills（skills-agent-proto 格式）
  /api/prompt           → 返回 system prompt 摘要
  /api/chat/stream      → 聊天流式输出 (SSE)，事件格式映射
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config
from nacos_skill_client.router import SkillRouter
from nacos_skill_client.utils import create_llm_client

# 延迟导入，避免循环依赖
def _get_client():
    from . import dependencies
    return dependencies.get_client()

def _get_config():
    from . import dependencies
    return dependencies.get_config()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["compat"])


@router.get("/skills", summary="兼容端点: 获取所有 Skills（skills-agent-proto 格式）")
def get_skills(
    namespace_id: str = "public",
    client: NacosSkillClient = Depends(_get_client),
    config: Config = Depends(_get_config),
):
    """返回 skills-agent-proto web 前端期望的格式。

    前端期望: { "skills": [{ "name", "description", "path" }] }
    """
    items = client.get_all_skills(namespace_id=namespace_id, page_size=500)
    skills = [
        {"name": s.name, "description": s.description, "path": ""}
        for s in items
    ]
    return {"skills": skills}


@router.get("/prompt", summary="兼容端点: 返回 System Prompt")
def get_prompt(
    config: Config = Depends(_get_config),
    client: NacosSkillClient = Depends(_get_client),
):
    """返回路由时使用的 System Prompt。"""
    max_count = config.skill_loader.max_metadata_count
    metadata_list = client.scan_skills_metadata(namespace_id=config.nacos.namespace_id, max_count=max_count)

    lines = ["You are a helpful coding assistant with access to specialized skills."]
    lines.append("")
    lines.append("## Available Skills")
    for meta in metadata_list:
        desc = (meta.description or "")[:120]
        lines.append(f"- **{meta.name}**: {desc}")

    prompt = "\n".join(lines)
    return {"prompt": prompt}


@router.get("/chat/stream", summary="兼容端点: 聊天流式输出 (SSE)")
def chat_stream(
    message: str,
    thread_id: str = "",
    client: NacosSkillClient = Depends(_get_client),
    config: Config = Depends(_get_config),
):
    """将 skills-agent-proto 的 SSE 事件格式映射到我们的路由结果。

    事件映射:
    - route → tool_call(load_skill) + text("使用 Skill: xxx")
    - content → text
    - done → done
    - error → agent_error
    """
    logger.info("chat_stream: thread_id=%s, message=%s", thread_id, message[:50])

    def event_generator():
        llm_client = create_llm_client(
            config.llm.base_url, config.llm.api_key, config.llm.timeout,
        )
        skill_router = SkillRouter.create_llm(
            llm_client,
            model=config.llm.model,
            temperature=config.router.routing_temperature,
            max_tokens=config.router.routing_max_tokens,
        )

        # 获取所有 Skills 并路由
        skills = client.get_all_skills()[: config.router.max_skills_for_routing]
        route_result = skill_router.route(skills, message)
        logger.info("chat_stream: route skill=%s, reason=%s", route_result.skill_name or "N/A", route_result.reason[:80])

        if route_result.skill_name:
            # 发送 skill 选中 → tool_call(load_skill) + text
            yield {"event": "tool_call", "data": json.dumps({
                "id": f"skill-{thread_id}",
                "name": "load_skill",
                "args": {"skill_name": route_result.skill_name},
            }, ensure_ascii=False)}
            yield {"event": "text", "data": json.dumps({
                "content": f"使用 Skill: {route_result.skill_name}\n",
            }, ensure_ascii=False)}

            try:
                # 获取指令文件
                file_label, skill_md = client.get_instruction_file(
                    route_result.skill_name, "",
                    priority=config.router.instruction_file_priority,
                )
                if skill_md:
                    skill_md = skill_md[:5000]  # 截断
                    logger.info("chat_stream: instruction loaded (%s, %d chars)", file_label, len(skill_md))

                # 调用 LLM 获取回复
                prompt = (
                    f"下面的内容是 {route_result.skill_name} 的指令文件（{file_label}），"
                    f"请按照以上指令，帮助用户解决问题。\n\n"
                    f"--- 指令开始 ---\n{skill_md}\n--- 指令结束 ---\n\n"
                    f"用户问题：\n{message}\n"
                )
                resp = llm_client.chat.completions.create(
                    model=config.llm.model,
                    messages=[
                        {"role": "system", "content": "你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=config.llm.temperature,
                    max_tokens=config.llm.max_tokens,
                    stream=True,
                )
                for chunk in resp:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield {"event": "text", "data": json.dumps({
                            "content": chunk.choices[0].delta.content,
                        }, ensure_ascii=False)}

            except Exception as exc:
                logger.error("chat_stream: skill execution failed: %s", exc, exc_info=True)
                yield {"event": "agent_error", "data": json.dumps({
                    "message": f"Skill 执行失败: {exc}",
                }, ensure_ascii=False)}
                yield {"event": "done", "data": json.dumps({"response": ""})}
                return
        else:
            # 没有选中 skill，直接调用 LLM
            resp = llm_client.chat.completions.create(
                model=config.llm.model,
                messages=[{"role": "user", "content": message}],
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
                stream=True,
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield {"event": "text", "data": json.dumps(
                        {"content": chunk.choices[0].delta.content},
                        ensure_ascii=False,
                    )}

        yield {"event": "done", "data": json.dumps({"response": ""})}

    return EventSourceResponse(event_generator())
