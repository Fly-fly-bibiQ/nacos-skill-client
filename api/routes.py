"""路由定义 — 仅保留 Nacos Skill 管理端点 + Skill ZIP 下载。

已移除:
- Skill 路由执行 (/skills/route)
- 流式路由执行 (/skills/route/stream)
- 所有 LLM 相关调用
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from nacos_skill_client import NacosNotFoundError
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.exceptions import NacosAPIError
from nacos_skill_client.config import Config

from . import dependencies
from .schemas import (
    SkillMetadataListResponse,
    SkillMetadataResponse,
)

get_client = dependencies.get_client
get_config = dependencies.get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["skills"])


# --------------------------------------------------------------------------- #
# Skill 元数据 / 列表端点
# --------------------------------------------------------------------------- #


@router.get("/skills/metadata", summary="获取所有 Skill 元数据（Level 1 发现）")
def get_skills_metadata(
    namespace_id: str = "public",
    client: NacosSkillClient = Depends(get_client),
    config: Config = Depends(get_config),
):
    """Level 1 元数据发现端点。

    仅返回 name + description，不加载完整 SKILL.md 内容。
    用于系统 prompt 注入和路由发现。
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


# --------------------------------------------------------------------------- #
# Skill 详情端点
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# 指令文件端点
# --------------------------------------------------------------------------- #


@router.get("/skills/{name}/md/{version}", summary="获取 SKILL.md")
def get_skill_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 SKILL.md，支持离线 Skill 回退。"""
    logger.info("get_skill_md: name=%s, version=%s", name, version)
    content = client.get_skill_md(name, version)
    if content is None:
        logger.warning("get_skill_md: NOT FOUND name=%s, version=%s", name, version)
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 SKILL.md")
    logger.info("get_skill_md: name=%s → %d chars", name, len(content.get("content", "")))
    return {
        "file_name": "SKILL.md",
        "content": content.get("content", ""),
        "frontmatter": content.get("frontmatter", {}),
    }


@router.get("/skills/{name}/agents/{version}", summary="获取 AGENTS.md")
def get_agents_md(name: str, version: str, client: NacosSkillClient = Depends(get_client)):
    """获取 AGENTS.md，支持离线 Skill 回退。"""
    logger.info("get_agents_md: name=%s, version=%s", name, version)
    content = client.get_agents_md(name, version)
    if content is None:
        logger.warning("get_agents_md: NOT FOUND name=%s, version=%s", name, version)
        raise NacosNotFoundError(f"无法获取 {name} v{version} 的 AGENTS.md")
    logger.info("get_agents_md: name=%s → %d chars", name, len(content.get("content", "")))
    return {
        "file_name": "AGENTS.md",
        "content": content.get("content", ""),
        "frontmatter": content.get("frontmatter", {}),
    }


# --------------------------------------------------------------------------- #
# Skill ZIP 下载端点（调用 Nacos 官方 3.4 API）
# --------------------------------------------------------------------------- #


@router.get("/skills/{name}/zip/{version}", summary="下载 Skill ZIP 包")
def download_skill_zip(name: str, version: str, namespace_id: str = "public", client: NacosSkillClient = Depends(get_client)):
    """通过 Nacos 官方 API 下载 Skill ZIP 包。

    对应 Nacos Open API 3.4:
    GET /nacos/v3/client/ai/skills?name=xxx&version=xxx
    """
    logger.info("download_skill_zip: name=%s, version=%s", name, version)
    try:
        zip_data = client.download_skill_zip(name=name, version=version, namespace_id=namespace_id)
    except NacosNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NacosAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    safe_name = "".join(
        c if c.isascii() and (c.isalnum() or c in ('-', '_')) else '_'
        for c in name
    ) or "skill"
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-{version}.zip"'},
    )


@router.get("/skills/{name}/zip", summary="下载 Skill ZIP 包（最新版）")
def download_skill_zip_latest(name: str, namespace_id: str = "public", client: NacosSkillClient = Depends(get_client)):
    """下载最新版本的 Skill ZIP 包（不传 version，Nacos 返回 latest）。"""
    logger.info("download_skill_zip_latest: name=%s", name)
    try:
        zip_data = client.download_skill_zip(name=name, namespace_id=namespace_id)
    except NacosNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NacosAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    safe_name = "".join(
        c if c.isascii() and (c.isalnum() or c in ('-', '_')) else '_'
        for c in name
    ) or "skill"
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
