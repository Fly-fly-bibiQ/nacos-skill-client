"""路由定义 + SSE 流式。"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends
from openai import OpenAI
from sse_starlette.sse import EventSourceResponse

from nacos_skill_client import NacosNotFoundError
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.config import Config
from nacos_skill_client.router import SkillRouter, route_and_execute
from nacos_skill_client.utils import create_llm_client

from . import dependencies
from .schemas import ListRequest, RouteRequest, RouteResponse, SearchRequest

get_client = dependencies.get_client
get_config = dependencies.get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["skills"])


@router.get("/skills/search", summary="搜索 Skills")
def search_skills(
    keyword: str = "",
    namespace_id: str = "public",
    page_no: int = 1,
    page_size: int = 50,
    client: NacosSkillClient = Depends(get_client),
):
    result = client.search_skills(keyword=keyword, namespace_id=namespace_id, page_no=page_no, page_size=page_size)
    return {
        "total_count": result.total_count,
        "page_number": result.page_number,
        "pages_available": result.pages_available,
        "items": [s.model_dump() for s in result.page_items],
    }


@router.get("/skills", summary="列出 Skills")
def list_skills(
    namespace_id: str = "public",
    page_no: int = 1,
    page_size: int = 50,
    client: NacosSkillClient = Depends(get_client),
):
    result = client.list_skills(namespace_id=namespace_id, page_no=page_no, page_size=page_size)
    return {
        "total_count": result.total_count,
        "page_number": result.page_number,
        "pages_available": result.pages_available,
        "items": [s.model_dump() for s in result.page_items],
    }


@router.get("/skills/all", summary="获取所有 Skills")
def get_all_skills(
    namespace_id: str = "public",
    page_size: int = 200,
    client: NacosSkillClient = Depends(get_client),
):
    items = client.get_all_skills(namespace_id=namespace_id, page_size=page_size)
    return {"total_count": len(items), "items": [s.model_dump() for s in items]}


@router.get("/skills/{name}", summary="获取 Skill 详情")
def get_skill_detail(name: str, client: NacosSkillClient = Depends(get_client)):
    detail = client.get_skill_detail(name)
    return detail.model_dump()


@router.get("/skills/{name}/versions/{version}", summary="获取 Skill 版本详情")
def get_skill_version(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    detail = client.get_skill_version_detail(name, version)
    return detail.model_dump()


@router.get("/skills/{name}/md/{version}", summary="获取 SKILL.md")
def get_skill_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 SKILL.md，支持离线 Skill 回退。"""
    content = client.get_skill_md(name, version)
    if content is None:
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 SKILL.md")
    return {"file_name": "SKILL.md", "content": content}


@router.get("/skills/{name}/agents/{version}", summary="获取 AGENTS.md")
def get_agents_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 AGENTS.md，支持离线 Skill 回退。"""
    content = client.get_agents_md(name, version)
    if content is None:
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 AGENTS.md")
    return {"file_name": "AGENTS.md", "content": content}


@router.post("/skills/route", summary="Skill 路由 + 执行", response_model=RouteResponse)
def route_skill(
    req: RouteRequest,
    client: NacosSkillClient = Depends(get_client),
    config: Config = Depends(get_config),
):
    start = time.time()
    llm_client = create_llm_client(config.llm.base_url, config.llm.api_key, config.llm.timeout)

    if req.strategy == "keyword":
        skill_router = SkillRouter.create_keyword()
    else:
        skill_router = SkillRouter.create_llm(
            llm_client,
            model=config.llm.model,
            temperature=config.router.routing_temperature,
            max_tokens=config.router.routing_max_tokens,
        )

    skills = client.get_all_skills()
    limited = skills[: config.router.max_skills_for_routing]
    route_result = skill_router.route(limited, req.query)

    answer = ""
    skill_md = None
    if route_result.skill_name:
        try:
            file_label, skill_md = client.get_instruction_file(
                route_result.skill_name, "",
                priority=config.router.instruction_file_priority,
            )
            if skill_md is None:
                skill_md = ""
            prompt = (
                f"下面的内容是 {route_result.skill_name} 的指令文件（{file_label}），"
                f"请按照以上指令，帮助用户解决问题。\n\n"
                f"--- 指令开始 ---\n{skill_md}\n--- 指令结束 ---\n\n"
                f"用户问题：\n{req.query}\n"
            )
            resp = llm_client.chat.completions.create(
                model=config.llm.model,
                messages=[
                    {"role": "system", "content": "你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
            )
            answer = resp.choices[0].message.content
        except Exception as exc:
            logger.error("路由执行失败: %s", exc)
            answer = f"⚠️ 获取 Skill 内容失败: {exc}"
            answer = f"⚠️ 获取 Skill 内容失败: {exc}"
    else:
        resp = llm_client.chat.completions.create(
            model=config.llm.model,
            messages=[{"role": "user", "content": req.query}],
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
        answer = resp.choices[0].message.content

    took_ms = int((time.time() - start) * 1000)
    return RouteResponse(
        query=req.query,
        route=route_result.to_dict(),
        skill_md=skill_md,
        answer=answer,
        took_ms=took_ms,
    )


@router.post("/skills/route/stream", summary="Skill 路由 + 流式执行")
def route_skill_stream(
    req: RouteRequest,
    client: NacosSkillClient = Depends(get_client),
    config: Config = Depends(get_config),
):
    llm_client = create_llm_client(config.llm.base_url, config.llm.api_key, config.llm.timeout)

    if req.strategy == "keyword":
        skill_router = SkillRouter.create_keyword()
    else:
        skill_router = SkillRouter.create_llm(
            llm_client,
            model=config.llm.model,
            temperature=config.router.routing_temperature,
            max_tokens=config.router.routing_max_tokens,
        )

    skills = client.get_all_skills()
    limited = skills[: config.router.max_skills_for_routing]
    route_result = skill_router.route(limited, req.query)

    def event_generator():
        # 发送路由结果
        yield {"event": "route", "data": json.dumps(route_result.to_dict(), ensure_ascii=False)}

        if route_result.skill_name:
            yield {"event": "skill_selected", "data": json.dumps({"skill_name": route_result.skill_name})}
            try:
                file_label, skill_md = client.get_instruction_file(
                    route_result.skill_name, "",
                    priority=config.router.instruction_file_priority,
                )
                if skill_md is None:
                    skill_md = ""
                yield {"event": "instruction_loaded", "data": json.dumps({"file_label": file_label, "length": len(skill_md)})}

                prompt = (
                    f"下面的内容是 {route_result.skill_name} 的指令文件（{file_label}），"
                    f"请按照以上指令，帮助用户解决问题。\n\n"
                    f"--- 指令开始 ---\n{skill_md}\n--- 指令结束 ---\n\n"
                    f"用户问题：\n{req.query}\n"
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
                        yield {"event": "content", "data": chunk.choices[0].delta.content}
            except Exception as exc:
                logger.error("路由流式执行失败: %s", exc)
                yield {"event": "error", "data": json.dumps({"error": str(exc)})}
        else:
            yield {"event": "no_skill", "data": json.dumps({"reason": route_result.reason})}
            resp = llm_client.chat.completions.create(
                model=config.llm.model,
                messages=[{"role": "user", "content": req.query}],
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
                stream=True,
            )
            for chunk in resp:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield {"event": "content", "data": chunk.choices[0].delta.content}

        yield {"event": "done", "data": json.dumps({"status": "complete"})}

    return EventSourceResponse(event_generator())


