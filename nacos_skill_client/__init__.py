"""Nacos Skill Registry Python 客户端。

通过 Nacos 3.x 的 AgentSpec API 管理 AI Skills。

特性:
- 自动 token 管理与刷新
- 搜索 / 列出 / 获取详情 / 获取版本内容 / 删除 Skills
- 类型提示 + 完整错误处理
- 支持上下文管理器 (with 语句)
"""

from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.exceptions import (
    NacosAPIError,
    NacosAuthError,
    NacosNotFoundError,
    NacosSkillError,
    NacosVersionError,
)
from nacos_skill_client.models import (
    SkillDetail,
    SkillItem,
    SkillListResult,
    SkillResourceFile,
    SkillVersionDetail,
    SkillVersionInfo,
)

__all__ = [
    # Client
    "NacosSkillClient",
    # Models
    "SkillItem",
    "SkillListResult",
    "SkillDetail",
    "SkillVersionInfo",
    "SkillVersionDetail",
    "SkillResourceFile",
    # Exceptions
    "NacosSkillError",
    "NacosAuthError",
    "NacosNotFoundError",
    "NacosAPIError",
    "NacosVersionError",
]

__version__ = "0.1.0"
