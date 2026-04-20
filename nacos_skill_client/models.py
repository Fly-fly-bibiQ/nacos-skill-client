"""Nacos Skill Registry 数据模型（Pydantic v2）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _safe_dict(value: Any) -> dict[str, str]:
    """安全地将值转为 dict[str, str]。"""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {}


def _safe_list(value: Any) -> list:
    """安全地将值转为 list。"""
    if isinstance(value, list):
        return value
    return []


def _safe_bool(value: Any, default: bool = True) -> bool:
    """安全地将值转为 bool。"""
    if isinstance(value, bool):
        return value
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    """安全地将值转为 int。"""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _ts_to_datetime(ts: int) -> datetime | None:
    """将毫秒时间戳转为 datetime。"""
    if ts is None or ts == 0:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# 版本信息
# --------------------------------------------------------------------------- #


class SkillVersionInfo(BaseModel):
    """单个版本信息。"""
    model_config = ConfigDict(populate_by_name=True)

    version: str = Field(default="", description="版本号")
    status: str = Field(default="", description="状态")
    author: str = Field(default="", description="作者")
    description: str = Field(default="", description="描述")
    create_time: int = Field(default=0, alias="createTime", description="创建时间（毫秒时间戳）")
    update_time: int = Field(default=0, alias="updateTime", description="更新时间（毫秒时间戳）")
    publish_pipeline_info: Any = Field(default=None, alias="publishPipelineInfo", description="发布流水线信息")
    download_count: int = Field(default=0, alias="downloadCount", description="下载次数")

    @property
    def create_time_dt(self) -> datetime | None:
        """创建时间的 datetime 形式。"""
        return _ts_to_datetime(self.create_time)

    @property
    def update_time_dt(self) -> datetime | None:
        """更新时间的 datetime 形式。"""
        return _ts_to_datetime(self.update_time)


# --------------------------------------------------------------------------- #
# Skill 列表项
# --------------------------------------------------------------------------- #


class SkillItem(BaseModel):
    """列表中的单个 Skill 元信息。"""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    namespace_id: str = Field(default="", alias="namespaceId")
    name: str = Field(default="", description="Skill 名称")
    description: str = Field(default="", description="Skill 描述")
    update_time: int = Field(default=0, alias="updateTime")
    enable: bool = Field(default=True)
    status: str = Field(default="", description="在线状态 (online/offline)")
    biz_tags: str = Field(default="", alias="bizTags")
    from_source: str = Field(default="", alias="from")
    scope: str = Field(default="")
    labels: dict[str, str] = Field(default_factory=dict)
    editing_version: str | None = Field(default=None, alias="editingVersion")
    reviewing_version: str | None = Field(default=None, alias="reviewingVersion")
    online_cnt: int = Field(default=0, alias="onlineCnt")
    download_count: int = Field(default=0, alias="downloadCount")

    @field_validator("namespace_id", mode="before")
    @classmethod
    def validate_namespace(cls, v: Any) -> str:
        return v or ""

    @field_validator("update_time", mode="before")
    @classmethod
    def validate_update_time(cls, v: Any) -> int:
        if v is None:
            return 0
        return int(v) if v else 0

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: Any) -> dict[str, str]:
        return _safe_dict(v) if v else {}

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> str:
        return str(v) if v else ""

    @field_validator("enable", mode="before")
    @classmethod
    def validate_enable(cls, v: Any) -> bool:
        if v is None:
            return True
        return bool(v)

    @property
    def update_time_dt(self) -> datetime | None:
        return _ts_to_datetime(self.update_time)


# --------------------------------------------------------------------------- #
# Skill 列表结果
# --------------------------------------------------------------------------- #


class SkillListResult(BaseModel):
    """Skill 列表查询结果。"""
    model_config = ConfigDict(populate_by_name=True)

    total_count: int = Field(default=0, alias="totalCount", description="总数")
    page_number: int = Field(default=1, alias="pageNumber", description="当前页码")
    pages_available: int = Field(default=0, alias="pagesAvailable", description="总页数")
    page_items: list[SkillItem] = Field(default_factory=list, alias="pageItems", description="当前页数据")


# --------------------------------------------------------------------------- #
# Skill 详情
# --------------------------------------------------------------------------- #


class SkillDetail(BaseModel):
    """Skill 详情。

    支持两种 API 返回格式：
    - Console API（带 version）：包含 versions 列表和 resource 对象
    - Client API（不带 version）：直接包含 content 和 resource 字段

    frontmatter 优先级高于 description 字段。
    """
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    namespace_id: str = Field(default="", alias="namespaceId")
    name: str = Field(default="")
    description: str = Field(default="")
    # frontmatter 提取的元信息（优先级高于 description）
    frontmatter: dict[str, str] = Field(default_factory=dict, description="从 AGENTS.md frontmatter 提取的 name/description")
    scope: str = Field(default="")
    enable: bool = Field(default=True)
    status: str = Field(default="", description="在线状态 (online/offline)")
    from_source: str = Field(default="", alias="from")
    biz_tags: str = Field(default="", alias="bizTags")
    labels: dict[str, str] = Field(default_factory=dict)
    versions: list[SkillVersionInfo] = Field(default_factory=list, alias="versions")
    editing_version: str | None = Field(default=None, alias="editingVersion")
    reviewing_version: str | None = Field(default=None, alias="reviewingVersion")
    online_cnt: int = Field(default=0, alias="onlineCnt")
    download_count: int = Field(default=0, alias="downloadCount")
    # Client API（不带 version 参数）直接返回的字段
    content: str = Field(default="", description="Skill 内容（Client API 直接返回）")
    resource: dict[str, SkillResourceFile] | dict[str, Any] = Field(
        default_factory=dict, description="资源文件（Client API 直接返回）",
    )

    @field_validator("namespace_id", mode="before")
    @classmethod
    def _v_ns(cls, v: Any) -> str:
        return v or ""

    @field_validator("biz_tags", mode="before")
    @classmethod
    def _v_bt(cls, v: Any) -> str:
        return v or ""

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, v: Any) -> dict[str, str]:
        return _safe_dict(v) if v else {}

    @field_validator("status", mode="before")
    @classmethod
    def _v_status(cls, v: Any) -> str:
        return str(v) if v else ""

    @field_validator("enable", mode="before")
    @classmethod
    def _v_enable(cls, v: Any) -> bool:
        return v if isinstance(v, bool) else True

    @field_validator("frontmatter", mode="before")
    @classmethod
    def validate_frontmatter(cls, v: Any) -> dict[str, str]:
        return _safe_dict(v) if v else {}

    @field_validator("versions", mode="before")
    @classmethod
    def validate_versions(cls, v: Any) -> list[SkillVersionInfo]:
        raw = _safe_list(v)
        return [SkillVersionInfo(**(item or {})) for item in raw]


# --------------------------------------------------------------------------- #
# 资源文件
# --------------------------------------------------------------------------- #


class SkillResourceFile(BaseModel):
    """Skill 版本中的资源文件。"""
    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field(default="", alias="fileName", description="文件名")
    content: str = Field(default="", description="文件内容")


# --------------------------------------------------------------------------- #
# Skill 版本详情
# --------------------------------------------------------------------------- #


class SkillVersionDetail(BaseModel):
    """Skill 版本详情。

    支持两种来源的返回格式：
    - 带 version 参数的 API 返回
    - 不带 version 参数的 API 回退格式（与 SkillDetail 结构相同）

    frontmatter 优先级高于 description 字段。
    """
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = Field(default="")
    namespace_id: str = Field(default="", alias="namespaceId")
    description: str = Field(default="")
    # frontmatter 提取的元信息（优先级高于 description）
    frontmatter: dict[str, str] = Field(default_factory=dict, description="从 AGENTS.md frontmatter 提取的 name/description")
    status: str = Field(default="", description="在线状态 (online/offline)")
    content: str = Field(default="")
    resource: dict[str, SkillResourceFile] = Field(default_factory=dict)
    biz_tags: str = Field(default="", alias="bizTags")
    # 回退格式中也可能有这些字段
    scope: str = Field(default="")
    enable: bool = Field(default=True)
    from_source: str = Field(default="", alias="from")
    labels: dict[str, str] = Field(default_factory=dict)
    editing_version: str | None = Field(default=None, alias="editingVersion")
    versions: list[SkillVersionInfo] = Field(default_factory=list, alias="versions")

    @field_validator("namespace_id", mode="before")
    @classmethod
    def _v_ns(cls, v: Any) -> str:
        return v or ""

    @field_validator("biz_tags", mode="before")
    @classmethod
    def _v_bt(cls, v: Any) -> str:
        return v or ""

    @field_validator("frontmatter", mode="before")
    @classmethod
    def validate_frontmatter(cls, v: Any) -> dict[str, str]:
        return _safe_dict(v) if v else {}

    @field_validator("resource", mode="before")
    @classmethod
    def validate_resource(cls, v: Any) -> dict[str, SkillResourceFile]:
        result: dict[str, SkillResourceFile] = {}
        for file_name, content in (v or {}).items():
            if isinstance(content, str):
                result[file_name] = SkillResourceFile(file_name=file_name, content=content)
            elif isinstance(content, dict):
                result[file_name] = SkillResourceFile(**content)
            else:
                result[file_name] = SkillResourceFile(file_name=file_name, content=str(content))
        return result


# --------------------------------------------------------------------------- #
# 路由相关模型
# --------------------------------------------------------------------------- #


class SkillBrief(BaseModel):
    """Skill 简要信息（用于路由，仅 name + description，节省 token）。

    从 frontmatter 提取 name/description，回退到 SkillDetail/SkillVersionDetail 字段。
    """
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(default="", description="Skill 名称")
    description: str = Field(default="", description="Skill 描述")


class RouteResult(BaseModel):
    """LLM 路由结果。"""
    model_config = ConfigDict(populate_by_name=True)

    skill_name: str | None = Field(default=None, description="推荐的 Skill 名称，null 表示不需要")
    reason: str = Field(default="", description="推荐理由")

    def to_dict(self) -> dict[str, Any]:
        return {"skill_name": self.skill_name, "reason": self.reason}


class RouteResponse(BaseModel):
    """路由 API 响应。"""
    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(description="用户查询")
    route: RouteResult = Field(description="路由结果")
    skill_md: str | None = Field(default=None, description="指令文件内容")
    answer: str = Field(description="最终回复")
    took_ms: int = Field(default=0, description="耗时（毫秒）")
