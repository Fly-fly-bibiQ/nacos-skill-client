"""Nacos Skill Registry Python 客户端。

通过 Nacos 3.x 的 AgentSpec API 管理 AI Skills。

特性:
- 自动 token 管理与刷新
- 搜索 / 列出 / 获取详情 / 获取版本内容
- 支持本地缓存
- 类型提示 + 完整错误处理
- 支持上下文管理器 (with 语句)

已移除: LLM 路由、Skill 路由执行等 LLM 依赖功能。
"""

from nacos_skill_client.cache import SkillCache
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.exceptions import (
    NacosAPIError,
    NacosAuthError,
    NacosNotFoundError,
    NacosSkillError,
    NacosVersionError,
)
from nacos_skill_client.models import (
    SkillBrief,
    SkillContent,
    SkillDetail,
    SkillItem,
    SkillListResult,
    SkillMetadata,
    SkillResourceFile,
    SkillVersionDetail,
    SkillVersionInfo,
)
from nacos_skill_client.utils import (
    build_prompt,
    extract_body,
    extract_frontmatter_content,
)

__all__ = [
    # Client
    "NacosSkillClient",
    # Cache
    "SkillCache",
    # Models
    "SkillItem",
    "SkillListResult",
    "SkillDetail",
    "SkillVersionInfo",
    "SkillVersionDetail",
    "SkillResourceFile",
    "SkillBrief",
    "SkillMetadata",
    "SkillContent",
    # Exceptions
    "NacosSkillError",
    "NacosAuthError",
    "NacosNotFoundError",
    "NacosAPIError",
    "NacosVersionError",
    # Utils
    "build_prompt",
    "extract_body",
    "extract_frontmatter_content",
]

__version__ = "0.2.0"
