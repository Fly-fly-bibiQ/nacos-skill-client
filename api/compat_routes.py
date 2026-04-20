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
from langchain_openai import ChatOpenAI
from sse_starlette.sse import EventSourceResponse

from nacos_skill_client.config import Config
from nacos_skill_client.router import SkillRouter
from nacos_skill_client.utils import create_llm_client

# 延迟导入，避免循环依赖
from agent.stream import stream_agent_response

def _get_config():
    from . import dependencies
    return dependencies.get_config()

def _get_client(config: Config = Depends(_get_config)):
    from nacos_skill_client.cache import SkillCache
    from nacos_skill_client.client import NacosSkillClient
    cache = None
    if config.cache.enabled:
        cache = SkillCache(cache_dir=config.cache.dir)
    return NacosSkillClient(config=config, cache=cache)

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

    llm = create_llm_client(config.llm.base_url, config.llm.api_key, config.llm.timeout)
    llm_lc = ChatOpenAI(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
    skill_router = SkillRouter.create_llm(
        llm,
        model=config.llm.model,
        temperature=config.router.routing_temperature,
        max_tokens=config.router.routing_max_tokens,
    )

    def event_generator():
        try:
            # 用 LangGraph Agent 跑，然后映射为 skills-agent-proto 事件格式
            logger.info("event_generator: starting stream_agent_response")
            events = stream_agent_response(
                user_message=message,
                client=client,
                config=config,
                llm=llm_lc,
                router=skill_router,
            )
            for event in events:
                logger.info("event_generator: received event=%s", event["event"])
                # 映射: discovered → tool_call(load_skill) 或 text
                if event["event"] == "discovered":
                    # 不发送 discovered，前端不关心
                    continue
                elif event["event"] == "skill_selected":
                    skill = event["data"]["skill_name"]
                    yield {"event": "tool_call", "data": json.dumps({
                        "type": "tool_call",
                        "id": f"skill-{thread_id}",
                        "name": "load_skill",
                        "args": {"skill_name": skill},
                    }, ensure_ascii=False)}
                    yield {"event": "text", "data": json.dumps({
                        "type": "text",
                        "content": f"使用 Skill: {skill}\n",
                    }, ensure_ascii=False)}
                elif event["event"] == "no_skill":
                    # 直接走 LLM，跳过 tool_call
                    pass
                elif event["event"] == "instruction_loaded":
                    pass  # 内部状态，不暴露给前端
                elif event["event"] == "content":
                    yield {"event": "text", "data": json.dumps({
                        "type": "text",
                        "content": event["data"],
                    }, ensure_ascii=False)}
                elif event["event"] == "error":
                    yield {"event": "agent_error", "data": json.dumps({
                        "type": "error",
                        "message": event["data"].get("error", "unknown"),
                    }, ensure_ascii=False)}
                elif event["event"] == "done":
                    # event["data"] may be a JSON string or dict depending on source
                    d = event["data"]
                    if isinstance(d, str):
                        d = json.loads(d)
                    yield {"event": "done", "data": json.dumps({"type": "done", "response": d.get("response", "")})}
        except Exception as exc:
            logger.error("chat_stream: unexpected error: %s", exc, exc_info=True)
            yield {"event": "agent_error", "data": json.dumps({
                "type": "error",
                "message": str(exc),
            }, ensure_ascii=False)}
            yield {"event": "done", "data": json.dumps({"type": "done", "response": ""})}

    return EventSourceResponse(event_generator())
