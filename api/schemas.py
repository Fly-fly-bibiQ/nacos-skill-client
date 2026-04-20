"""API 数据模型（Pydantic）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    keyword: str = Field(default="", description="搜索关键词")
    namespace_id: str = Field(default="public", description="命名空间")
    page_no: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=200, description="每页数量")


class ListRequest(BaseModel):
    namespace_id: str = Field(default="public", description="命名空间")
    page_no: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=200, description="每页数量")


class RouteRequest(BaseModel):
    """路由请求。"""

    query: str = Field(..., description="用户查询")
    keyword: str = Field(default="", description="Nacos 搜索关键词（可选）")
    namespace_id: str = Field(default="public", description="命名空间")
    strategy: str = Field(default="llm", description="路由策略: llm | keyword")


class RouteResponse(BaseModel):
    """路由响应。"""

    query: str
    route: dict[str, str | None]
    skill_md: str | None
    answer: str
    took_ms: int
