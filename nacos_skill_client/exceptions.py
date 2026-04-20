"""Nacos Skill Registry 客户端异常定义。"""

from __future__ import annotations

import json
from typing import Any


class NacosSkillError(Exception):
    """Nacos Skill Registry 客户端的基础异常。

    Attributes:
        message: 异常描述信息。
        code: 错误码（HTTP 状态码或 Nacos 业务错误码）。
        response: 原始响应体。
    """

    def __init__(
        self,
        message: str,
        code: int | None = None,
        response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: int | None = code
        self.response: dict[str, Any] | None = response

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.code is not None:
            parts.append(f"[code={self.code}]")
        return " ".join(parts)


class NacosAuthError(NacosSkillError):
    """认证失败异常（token 过期、用户名/密码错误等）。"""


class NacosNotFoundError(NacosSkillError):
    """资源未找到异常（Skill 不存在等）。"""


class NacosAPIError(NacosSkillError):
    """Nacos API 返回错误（非 2xx 响应）。"""


class NacosVersionError(NacosSkillError):
    """版本相关错误（版本不存在、版本校验失败等）。"""


class NacosSkillNotFoundError(NacosSkillError):
    """Skill 未找到异常（比 NotFound 更具体）。"""


class RouterError(NacosSkillError):
    """路由错误（LLM 路由失败等）。"""

    def __init__(self, message: str, response: Any = None) -> None:
        super().__init__(message, code=None, response=response)
