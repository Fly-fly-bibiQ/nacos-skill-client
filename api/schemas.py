"""API 数据模型（Pydantic）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillMetadataResponse(BaseModel):
    """Skill 元数据响应（Level 1 发现结果）。"""

    name: str = Field(description="Skill 名称")
    description: str = Field(description="Skill 描述（何时使用）")


class SkillMetadataListResponse(BaseModel):
    """Skill 元数据列表响应。"""

    total_count: int = Field(description="总数量")
    skills: list[SkillMetadataResponse] = Field(description="Skill 元数据列表")


class SearchRequest(BaseModel):
    keyword: str = Field(default="", description="搜索关键词")
    namespace_id: str = Field(default="public", description="命名空间")
    page_no: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=200, description="每页数量")


class ListRequest(BaseModel):
    namespace_id: str = Field(default="public", description="命名空间")
    page_no: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=200, description="每页数量")


# --------------------------------------------------------------------------- #
# Agent 相关 Schema
# --------------------------------------------------------------------------- #


class ChatRequest(BaseModel):
    """Agent 对话请求。"""

    message: str = Field(description="用户消息")
    thread_id: str = Field(default="default", description="对话线程 ID（用于记忆）")


class ChatResponse(BaseModel):
    """Agent 对话响应。"""

    answer: str = Field(description="Agent 回答")
    tool_used: str | None = Field(default=None, description="使用的工具名称")
    thinking_steps: list[str] = Field(default_factory=list, description="思考步骤")
    took_ms: float = Field(description="耗时（毫秒）")


class ToolInfo(BaseModel):
    """Tool 信息。"""

    name: str = Field(description="Tool 名称")
    description: str = Field(description="Tool 描述")


class ToolsListResponse(BaseModel):
    """Tools 列表响应。"""

    tools: list[ToolInfo] = Field(description="Tools 列表")
    total: int = Field(description="总数")


class ReloadResponse(BaseModel):
    """重新加载响应。"""

    status: str = Field(description="状态")
    loaded: int = Field(description="加载数量")
    total: int = Field(description="总数")
    time_ms: float = Field(description="耗时（毫秒）")
    agent_initialized: bool = Field(description="Agent 是否已初始化")
