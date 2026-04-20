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
from .schemas import (
    ListRequest,
    RouteRequest,
    RouteResponse,
    SearchRequest,
    SkillMetadataListResponse,
    SkillMetadataResponse,
)

get_client = dependencies.get_client
get_config = dependencies.get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["skills"])


@router.get("/skills/metadata", summary="获取所有 Skill 元数据（Level 1 发现）")
def get_skills_metadata(
    namespace_id: str = "public",
    client: NacosSkillClient = Depends(get_client),
    config: Config = Depends(get_config),
):
    """Level 1 元数据发现端点。

    类似 skills-agent-proto 的 SkillLoader.scan_skills()
    仅返回 name + description，不加载完整 SKILL.md 内容。
    用于系统 prompt 注入和路由发现。

    响应示例:
    ```json
    {
      "total_count": 3,
      "skills": [
        {"name": "翻译助手", "description": "翻译文本"},
        {"name": "代码生成", "description": "生成代码"},
        {"name": "天气查询", "description": "查询天气"}
      ]
    }
    ```
    """
    max_count = config.skill_loader.max_metadata_count
    logger.info("get_skills_metadata: namespace=%s, max_count=%d", namespace_id, max_count)
    metadata_list = client.scan_skills_metadata(namespace_id=namespace_id, max_count=max_count)
    logger.info("get_skills_metadata: found %d skills", len(metadata_list))
    return SkillMetadataListResponse(
        total_count=len(metadata_list),
        skills=[
            SkillMetadataResponse(name=m.name, description=m.description)
            for m in metadata_list
        ],
    )


@router.get("/skills/search", summary="搜索 Skills")
def search_skills(
    keyword: str = "",
    namespace_id: str = "public",
    page_no: int = 1,
    page_size: int = 50,
    client: NacosSkillClient = Depends(get_client),
):
    logger.debug("search_skills: keyword=%s, page_no=%d, page_size=%d", keyword, page_no, page_size)
    result = client.search_skills(keyword=keyword, namespace_id=namespace_id, page_no=page_no, page_size=page_size)
    logger.info("search_skills: keyword=%s → %d total", keyword, result.total_count)
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
    logger.info("list_skills: page %d/%d, count=%d, total=%d", page_no, result.pages_available, len(result.page_items), result.total_count)
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
    logger.info("get_all_skills: page_size=%d", page_size)
    items = client.get_all_skills(namespace_id=namespace_id, page_size=page_size)
    logger.info("get_all_skills: got %d skills total", len(items))
    return {"total_count": len(items), "items": [s.model_dump() for s in items]}


@router.get("/skills/{name}", summary="获取 Skill 详情")
def get_skill_detail(name: str, client: NacosSkillClient = Depends(get_client)):
    logger.info("get_skill_detail: name=%s", name)
    detail = client.get_skill_detail(name)
    return detail.model_dump()


@router.get("/skills/{name}/versions/{version}", summary="获取 Skill 版本详情")
def get_skill_version(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    logger.info("get_skill_version: name=%s, version=%s", name, version)
    detail = client.get_skill_version_detail(name, version)
    return detail.model_dump()


@router.get("/skills/{name}/md/{version}", summary="获取 SKILL.md")
def get_skill_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 SKILL.md，支持离线 Skill 回退。"""
    logger.info("get_skill_md: name=%s, version=%s", name, version)
    content = client.get_skill_md(name, version)
    if content is None:
        logger.warning("get_skill_md: NOT FOUND name=%s, version=%s", name, version)
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 SKILL.md")
    logger.info("get_skill_md: name=%s → %d chars", name, len(content))
    return {"file_name": "SKILL.md", "content": content}


@router.get("/skills/{name}/agents/{version}", summary="获取 AGENTS.md")
def get_agents_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 AGENTS.md，支持离线 Skill 回退。"""
    logger.info("get_agents_md: name=%s, version=%s", name, version)
    content = client.get_agents_md(name, version)
    if content is None:
        logger.warning("get_agents_md: NOT FOUND name=%s, version=%s", name, version)
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 AGENTS.md")
    logger.info("get_agents_md: name=%s → %d chars", name, len(content))
    return {"file_name": "AGENTS.md", "content": content}


@router.post("/skills/route", summary="Skill 路由 + 执行", response_model=RouteResponse)
def route_skill(
    req: RouteRequest,
    client: NacosSkillClient = Depends(get_client),
    config: Config = Depends(get_config),
):
    start = time.time()
    logger.info("route_skill: query=%s (first 50 chars), strategy=%s", req.query[:50], req.strategy)

    llm_client = create_llm_client(config.llm.base_url, config.llm.api_key, config.llm.timeout)

    if req.strategy == "keyword":
        logger.debug("route_skill: creating keyword router")
        skill_router = SkillRouter.create_keyword()
    else:
        logger.debug("route_skill: creating LLM router (model=%s)", config.llm.model)
        skill_router = SkillRouter.create_llm(
            llm_client,
            model=config.llm.model,
            temperature=config.router.routing_temperature,
            max_tokens=config.router.routing_max_tokens,
        )

    skills = client.get_all_skills()
    limited = skills[: config.router.max_skills_for_routing]
    logger.debug("route_skill: loaded %d skills for routing", len(limited))

    route_result = skill_router.route(limited, req.query)
    logger.info("route_skill: matched skill=%s, reason=%s", route_result.skill_name or "N/A", route_result.reason[:100])

    answer = ""
    skill_md = None
    if route_result.skill_name:
        try:
            logger.info("route_skill: fetching instruction for skill=%s", route_result.skill_name)
            file_label: str | None = None
            if client.cache and client.cache.has_skill(route_result.skill_name):
                logger.info("route_skill: cache hit for skill=%s", route_result.skill_name)
                file_label, skill_md = client.cache.get_skill_file(
                    route_result.skill_name, "AGENTS.md",
                )
                if skill_md is None:
                    # manifest exists but file missing, fall through to download
                    logger.info("route_skill: cache manifest found but file missing, downloading")
                    file_label = None
                    skill_md = None
            if skill_md is None:
                file_label, skill_md = client.get_instruction_file(
                    route_result.skill_name, "",
                    priority=config.router.instruction_file_priority,
                )
            if skill_md is None:
                skill_md = ""
            # Cache the skill for future use
            if client.cache and file_label and skill_md:
                logger.info("route_skill: caching skill=%s (%s, %d chars)", route_result.skill_name, file_label, len(skill_md))
                client.cache.save_skill(route_result.skill_name, skill_md, file_label)
            logger.info("route_skill: instruction loaded (%s, %d chars), calling LLM", file_label or "unknown", len(skill_md))
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
            logger.info("route_skill: LLM response received (%d chars)", len(answer))
        except Exception as exc:
            logger.error("route_skill: skill execution failed for %s: %s", route_result.skill_name, exc, exc_info=True)
            answer = f"⚠️ 获取 Skill 内容失败: {exc}"
    else:
        logger.info("route_skill: no skill matched, calling LLM directly")
        resp = llm_client.chat.completions.create(
            model=config.llm.model,
            messages=[{"role": "user", "content": req.query}],
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
        answer = resp.choices[0].message.content
        logger.info("route_skill: LLM direct response received (%d chars)", len(answer))

    took_ms = int((time.time() - start) * 1000)
    logger.info("route_skill: completed in %dms, skill=%s", took_ms, route_result.skill_name or "N/A")
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
    logger.info("route_skill_stream: query=%s (first 50 chars), strategy=%s", req.query[:50], req.strategy)
    llm_client = create_llm_client(config.llm.base_url, config.llm.api_key, config.llm.timeout)

    if req.strategy == "keyword":
        logger.debug("route_skill_stream: creating keyword router")
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
    logger.info("route_skill_stream: matched skill=%s, reason=%s", route_result.skill_name or "N/A", route_result.reason[:100])

    def event_generator():
        # 发送路由结果
        yield {"event": "route", "data": json.dumps(route_result.to_dict(), ensure_ascii=False)}

        if route_result.skill_name:
            logger.info("route_skill_stream: selected skill=%s", route_result.skill_name)
            yield {"event": "skill_selected", "data": json.dumps({"skill_name": route_result.skill_name})}
            try:
                file_label: str | None = None
                skill_md: str | None = None
                # 尝试从缓存读取
                if client.cache and client.cache.has_skill(route_result.skill_name):
                    file_label, skill_md = client.cache.get_skill_file(
                        route_result.skill_name, "AGENTS.md",
                    )
                # 缓存未命中则从 Nacos 下载
                if skill_md is None:
                    file_label, skill_md = client.get_instruction_file(
                        route_result.skill_name, "",
                        priority=config.router.instruction_file_priority,
                    )
                # 缓存指令文件
                if client.cache and file_label and skill_md:
                    client.cache.save_skill(route_result.skill_name, skill_md, file_label)
                if skill_md is None:
                    skill_md = ""
                yield {"event": "instruction_loaded", "data": json.dumps({"file_label": file_label, "length": len(skill_md)})}
                logger.info("route_skill_stream: instruction loaded (%s, %d chars), starting LLM stream", file_label, len(skill_md))

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
                logger.info("route_skill_stream: LLM stream completed for skill=%s", route_result.skill_name)
            except Exception as exc:
                logger.error("route_skill_stream: skill stream failed for %s: %s", route_result.skill_name, exc, exc_info=True)
                yield {"event": "error", "data": json.dumps({"error": str(exc)})}
        else:
            logger.info("route_skill_stream: no skill matched, streaming LLM directly")
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
            logger.info("route_skill_stream: LLM direct stream completed")

        yield {"event": "done", "data": json.dumps({"status": "complete"})}

    return EventSourceResponse(event_generator())
