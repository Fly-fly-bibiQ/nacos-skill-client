"""Nacos Skill Registry Python 客户端。

通过 Nacos 3.x Client API 管理 AI Skills 和 AgentSpecs：
- 搜索 / 列出 Skills
- 获取 Skill 详情
- 获取 SKILL.md 内容
- 获取所有 Skills（便捷方法）
- 支持 Config 注入
- 四级回退策略处理 offline Skill
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

from nacos_skill_client.config import Config
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

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  解析函数
# --------------------------------------------------------------------------- #


def _parse_version_info(raw: dict[str, Any]) -> SkillVersionInfo:
    return SkillVersionInfo(**{k: v for k, v in (raw or {}).items()})


def _parse_skill_item(raw: dict[str, Any]) -> SkillItem:
    return SkillItem(**{k: v for k, v in (raw or {}).items()})


def _parse_skill_detail(raw: dict[str, Any]) -> SkillDetail:
    return SkillDetail(**{k: v for k, v in (raw or {}).items()})


def _parse_skill_version_detail(raw: dict[str, Any]) -> SkillVersionDetail:
    return SkillVersionDetail(**{k: v for k, v in (raw or {}).items()})


def _parse_skill_list_result(raw: dict[str, Any]) -> SkillListResult:
    """解析 Skill 列表结果（Console API / Client API 通用）。"""
    page_items_raw = raw.get("pageItems", []) if isinstance(raw, dict) else []
    items = [_parse_skill_item(item) for item in page_items_raw if item]
    return SkillListResult(
        total_count=raw.get("totalCount", len(items)) if isinstance(raw, dict) else len(items),
        page_number=raw.get("pageNumber", 1) if isinstance(raw, dict) else 1,
        pages_available=raw.get("pagesAvailable", 0) if isinstance(raw, dict) else 0,
        page_items=items,
    )


def _parse_frontmatter(content: str) -> dict[str, str]:
    """从 Markdown 内容中提取 YAML frontmatter 的 name/description。

    Args:
        content: Markdown 文档内容。

    Returns:
        dict 包含 name/description，未找到 frontmatter 返回空 dict。
    """
    if not content:
        return {}
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?', content, re.DOTALL)
    if not match:
        return {}
    fm_content = match.group(1)
    result: dict[str, str] = {}
    for line in fm_content.split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in ('name', 'description'):
                result[key] = value
    return result


# --------------------------------------------------------------------------- #
#  客户端
# --------------------------------------------------------------------------- #


class NacosSkillClient:
    """Nacos Skill Registry Client — 基于标准 Client API。

    使用 Nacos 3.x 官方 Client API 路径（/nacos/v3/client/ai/...）。

    典型用法::

        from nacos_skill_client import NacosSkillClient

        with NacosSkillClient() as client:
            skills = client.list_skills(page_size=20)
            for s in skills.page_items:
                print(s.name, s.description)
    """

    def __init__(
        self,
        config: Config | None = None,
        server_addr: str | None = None,
        username: str | None = None,
        password: str | None = None,
        namespace_id: str | None = None,
        timeout: int | None = None,
        verify_ssl: bool | None = None,
    ) -> None:
        """初始化客户端。

        Args:
            config: 配置实例。
            server_addr: Nacos 地址（如 http://192.168.1.118:8848）。
            username: Nacos 用户名。
            password: Nacos 密码。
            namespace_id: 默认命名空间。
            timeout: 请求超时秒数。
            verify_ssl: 是否验证 SSL 证书。
        """
        if config is not None:
            self.base_url: str = config.nacos.server_addr.rstrip("/")
            self.namespace_id: str = config.nacos.namespace_id
            self.timeout: int = config.nacos.timeout
            self.verify_ssl: bool = config.nacos.verify_ssl
        else:
            self.base_url = (server_addr or "http://192.168.1.118:8848").rstrip("/")
            self.namespace_id = namespace_id or "public"
            self.timeout = timeout or 30
            self.verify_ssl = verify_ssl if verify_ssl is not None else True

        self._username = username or "nacos"
        self._password = password or "nacos"
        self._session: requests.Session = requests.Session()
        self._session.verify = self.verify_ssl
        self._token: str | None = None
        self._client_version: str = "nacos-python-skill-client/1.0.0"

        # 自动登录
        self._login(self._username, self._password)

    @property
    def token(self) -> str | None:
        """当前认证 token。"""
        return self._token

    def _login(self, username: str, password: str) -> None:
        """登录 Nacos，获取 Bearer token。"""
        url = f"{self.base_url}/nacos/v1/auth/users/login"
        try:
            resp = self._session.post(
                url,
                data={"username": username, "password": password},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("accessToken")
            logger.info("Nacos login successful as %s", username)
            return
        except requests.RequestException as exc:
            raise NacosAuthError(f"登录失败: {exc}") from exc

    def _auth_header(self) -> dict[str, str]:
        """获取认证头。"""
        if not self._token:
            raise NacosAuthError("未登录")
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": self._client_version,
            "Client-Version": self._client_version,
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """发送请求。

        Args:
            method: HTTP 方法。
            path: API 路径（不含 /nacos 前缀）。
            params: 查询参数。

        Returns:
            API 返回的 data 字段内容。
        """
        url = f"{self.base_url}/nacos{path}"
        headers = self._auth_header()
        params = params or {}

        try:
            resp = self._session.request(
                method, url, headers=headers, params=params, timeout=self.timeout,
            )

            if resp.status_code == 401:
                # token 过期，重试登录
                self._login(self._username, self._password)
                headers = self._auth_header()
                resp = self._session.request(
                    method, url, headers=headers, params=params, timeout=self.timeout,
                )

            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    code = body.get("code", resp.status_code)
                    message = body.get("message", resp.text[:200])
                except ValueError:
                    code = resp.status_code
                    message = resp.text[:200]

                if resp.status_code == 404:
                    raise NacosNotFoundError(f"资源未找到: {path}", code=code)
                raise NacosAPIError(f"API 错误: {message}", code=code)

            json_resp = resp.json()
            if json_resp.get("code") == 0:
                return json_resp.get("data")
            return json_resp
        except requests.RequestException as exc:
            raise NacosSkillError(f"请求失败: {path}: {exc}") from exc

    def _request_console(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """发送请求（使用 /console API 路径，用于 Console API 调用）。

        Console API 用于获取离线 Skill 的元信息。
        """
        url = f"{self.base_url}/nacos{path}"
        headers = {
            "Authorization": f"Bearer {self._token}" if self._token else "",
            "Content-Type": "application/json",
        }
        params = params or {}

        try:
            resp = self._session.request(
                method, url, headers=headers, params=params, timeout=self.timeout,
            )

            if resp.status_code == 401:
                self._login(self._username, self._password)
                headers["Authorization"] = f"Bearer {self._token}"
                resp = self._session.request(
                    method, url, headers=headers, params=params, timeout=self.timeout,
                )

            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    message = body.get("message", resp.text[:200])
                except ValueError:
                    message = resp.text[:200]
                logger.debug("Console API %s %s 返回 %d: %s", method, path, resp.status_code, message)
                return None

            json_resp = resp.json()
            return json_resp.get("data")
        except requests.RequestException as exc:
            logger.debug("Console API 请求失败 %s %s: %s", method, path, exc)
            return None

    def _get_skill_resource_file(self, name: str, version: str, key: str) -> str | None:
        """获取 Skill 版本中的特定资源文件内容。

        Args:
            name: Skill 名称。
            version: 版本号。
            key: 资源 key（如 config_SKILL__md）。

        Returns:
            文件内容，不存在返回 None。
        """
        try:
            detail = self.get_skill_version_detail(name, version)
            resource = detail.resource or {}
            file_obj = resource.get(key)
            if file_obj is None:
                return None
            if isinstance(file_obj, str):
                return file_obj
            if isinstance(file_obj, dict):
                return file_obj.get('content', str(file_obj))
            return file_obj.content
        except (NacosNotFoundError, NacosVersionError):
            pass
        return None

    def get_instruction_file(self, name: str, version: str,
                             priority: list[str] | None = None) -> tuple[str, str] | None:
        """按优先级获取指令文件内容。

        四级回退策略：
        1. 优先：带 version 参数请求（如果 version 是 online 的）
        2. 降级：不带 version 参数请求（Skill 是 online 的）
        3. 降级：使用 Console API 查询（包含 offline 的 Skill 元信息）
        4. 降级：返回 None 并记录警告

        Args:
            name: Skill 名称。
            version: 版本号。
            priority: 文件优先级列表，如 ['SKILL.md', 'AGENTS.md', 'SOUL.md']。

        Returns:
            (file_label, content) 或 None。
        """
        if priority is None:
            priority = ['SKILL.md', 'AGENTS.md', 'SOUL.md']
        
        # 将文件标签映射到资源 key
        file_map = {
            'SKILL.md': 'config_SKILL__md',
            'AGENTS.md': 'config_AGENTS__md',
            'SOUL.md': 'config_SOUL__md',
            'IDENTITY.md': 'config_IDENTITY__md',
        }

        # 级别 1: 带 version 获取
        for label in priority:
            key = file_map.get(label, label)
            try:
                content = self._get_skill_resource_file(name, version, key)
            except (NacosNotFoundError, NacosAPIError, NacosVersionError):
                content = None
            if content:
                return (label, content)

        # 级别 2: 不带 version 获取（online 的 Skill）
        try:
            detail = self.get_skill_detail(name)
        except (NacosNotFoundError, NacosAPIError):
            detail = None
        if detail:
            resource_data = getattr(detail, 'resource', {}) or {}
            for label in priority:
                key = file_map.get(label, label)
                content = self._resolve_resource_content(resource_data, key)
                if content:
                    return (label, content)

        # 级别 3: Console API 获取（offline Skill）
        console_detail = self._get_skill_detail_with_console_api(name)
        if console_detail:
            resource_data = getattr(console_detail, 'resource', {}) or {}
            # 从 versions 中取最新的 content
            versions = getattr(console_detail, 'versions', []) or []
            if not resource_data and versions:
                latest = versions[-1]
                resource_data = latest.resource if hasattr(latest, 'resource') else {}
                # 如果没有 resource，尝试从 console API 的 raw data 中找
                if not resource_data:
                    content_val = getattr(console_detail, 'content', '') or ''
                    if content_val:
                        return (priority[0], content_val)
            for label in priority:
                key = file_map.get(label, label)
                content = self._resolve_resource_content(resource_data, key)
                if content:
                    return (label, content)

        # 级别 4: 返回 None
        logger.warning(
            "无法获取 Skill 指令文件: name=%s, version=%s (所有回退级别均失败)",
            name, version,
        )
        return None

    # ------------------------------------------------------------------ #
    #  Public API — 基于 Client API
    # ------------------------------------------------------------------ #

    def search_skills(
        self,
        keyword: str = "",
        namespace_id: str | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> SkillListResult:
        """搜索 / 分页列出 Skills。

        使用 Client API: GET /nacos/v3/client/ai/agentspecs/search
        """
        params: dict[str, Any] = {
            "namespaceId": namespace_id or self.namespace_id,
            "keyword": keyword,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        data = self._request("GET", "/v3/client/ai/agentspecs/search", params=params)
        if data is None:
            return SkillListResult()

        items = []
        page_items = data.get("pageItems", []) if isinstance(data, dict) else []
        for item in page_items:
            items.append(_parse_skill_item(item))

        return SkillListResult(
            total_count=data.get("totalCount", 0) if isinstance(data, dict) else len(items),
            page_number=data.get("pageNumber", page_no) if isinstance(data, dict) else page_no,
            pages_available=data.get("pagesAvailable", 0) if isinstance(data, dict) else 0,
            page_items=items,
        )

    def list_skills(
        self,
        namespace_id: str | None = None,
        page_no: int = 1,
        page_size: int = 20,
    ) -> SkillListResult:
        """列出 Skills（无关键词搜索）。"""
        return self.search_skills(keyword="", namespace_id=namespace_id, page_no=page_no, page_size=page_size)

    def get_all_skills(
        self,
        namespace_id: str | None = None,
        page_size: int = 200,
    ) -> list[SkillItem]:
        """获取所有 Skills（自动分页，包含 offline Skill）。

        增加对 offline Skill 的容错：如果列表接口返回空，尝试使用 Console API 获取。
        """
        all_items: list[SkillItem] = []
        page_no = 1
        while True:
            result = self.list_skills(namespace_id=namespace_id, page_no=page_no, page_size=page_size)
            all_items.extend(result.page_items)
            if page_no >= result.pages_available or result.pages_available == 0:
                break
            page_no += 1

        # 如果 Client API 没有返回任何结果，尝试 Console API 作为回退
        if not all_items:
            try:
                console_items = self._get_all_skills_from_console(namespace_id)
                if console_items:
                    logger.info(
                        "Client API 未返回 Skill，使用 Console API 回退获取到 %d 个",
                        len(console_items),
                    )
                    all_items = console_items
            except Exception as exc:
                logger.warning("Console API 回退失败: %s", exc)

        return all_items

    def _get_all_skills_from_console(
        self,
        namespace_id: str | None = None,
        page_size: int = 200,
    ) -> list[SkillItem]:
        """从 Console API 获取所有 Skills。

        作为 Client API 失败时的回退，可以获取 offline Skill。
        """
        all_items: list[SkillItem] = []
        page_no = 1
        while True:
            params: dict[str, Any] = {
                "namespaceId": namespace_id or self.namespace_id,
                "keyword": "",
                "pageNo": page_no,
                "pageSize": page_size,
            }
            data = self._request_console("GET", "/v3/console/ai/agentspecs/search", params=params)
            if data is None:
                break

            parsed = _parse_skill_list_result(data)
            all_items.extend(parsed.page_items)

            if page_no >= parsed.pages_available or parsed.pages_available == 0:
                break
            page_no += 1

        return all_items

    def get_skill_detail(
        self,
        name: str,
        namespace_id: str | None = None,
        version: str | None = None,
        label: str | None = None,
    ) -> SkillDetail:
        """获取 Skill 详情。

        使用 Client API: GET /nacos/v3/client/ai/agentspecs
        """
        params: dict[str, Any] = {
            "name": name,
            "namespaceId": namespace_id or self.namespace_id,
        }
        if version:
            params["version"] = version
        if label:
            params["label"] = label
        data = self._request("GET", "/v3/client/ai/agentspecs", params=params)
        if data is None:
            raise NacosNotFoundError(f"Skill 不存在: {name}", response={"name": name})
        return _parse_skill_detail(data)

    def get_skill_version_detail(
        self,
        name: str,
        version: str | None = None,
        namespace_id: str | None = None,
    ) -> SkillVersionDetail:
        """获取 Skill 版本详情（含 content + resource）。

        四级回退策略：
        1. 优先：带 version 参数请求（如果 version 是 online 的）
        2. 降级：不带 version 参数请求（Skill 是 online 的）
        3. 降级：使用 Console API `/v3/console/ai/agentspecs` 查询
           （包含 offline 的 Skill 元信息）
        4. 降级：返回 None 并记录警告
        """
        # 级别 1: 带 version 获取
        if version:
            try:
                detail = self.get_skill_detail(name, namespace_id=namespace_id, version=version)
                return _parse_skill_version_detail(
                    {**detail.model_dump(), "resource": detail.resource}
                    if hasattr(detail, 'resource')
                    else detail.model_dump(),
                )
            except (NacosNotFoundError, NacosAPIError, NacosVersionError) as exc:
                logger.warning(
                    "获取 Skill 指定版本详情失败 (name=%s, version=%s): %s，回退到不带 version 的请求",
                    name, version, exc,
                )

        # 级别 2: 不带 version 获取（online 的 Skill）
        try:
            detail = self.get_skill_detail(name, namespace_id=namespace_id)
            return self._parse_skill_version_detail_from_data(detail)
        except (NacosNotFoundError, NacosAPIError) as exc:
            logger.warning(
                "获取 Skill 详情失败 (name=%s): %s，回退到 Console API",
                name, exc,
            )

        # 级别 3: Console API 获取（offline Skill）
        try:
            console_detail = self._get_skill_detail_with_console_api(name, namespace_id)
            if console_detail:
                return self._parse_skill_version_detail_from_data(console_detail)
        except Exception as exc:
            logger.warning(
                "Console API 获取 Skill 详情失败 (name=%s): %s",
                name, exc,
            )

        # 级别 4: 返回 None
        logger.warning(
            "无法获取 Skill 详情 (name=%s, version=%s)，所有回退级别均失败",
            name, version or "(any)",
        )
        raise NacosNotFoundError(f"Skill 不存在或无法获取: {name}", response={"name": name})

    def _get_skill_detail_with_console_api(
        self,
        name: str,
        namespace_id: str | None = None,
    ) -> SkillDetail | None:
        """使用 Console API 获取 Skill 详情。

        Console API (`/v3/console/ai/agentspecs`) 返回的 Skill 信息
        包含 offline Skill，是 Client API 失败时的有效回退。

        Args:
            name: Skill 名称。
            namespace_id: 命名空间。

        Returns:
            SkillDetail 或 None。
        """
        params: dict[str, Any] = {
            "name": name,
            "namespaceId": namespace_id or self.namespace_id,
        }
        data = self._request_console("GET", "/v3/console/ai/agentspecs", params=params)
        if data is None:
            return None

        # Console API 返回格式可能和 Client API 不同
        # 尝试解析为 SkillDetail
        try:
            detail = _parse_skill_detail(data)
            # 如果解析成功且 name 匹配，返回
            if detail.name == name:
                return detail
        except Exception:
            pass

        # 如果直接解析失败，尝试手动构造
        # Console API 可能返回嵌套结构
        versions_raw = []
        if isinstance(data, dict):
            # Console API 可能返回 versionInfo 或 versions
            for key in ("versionInfo", "versions", "version"):
                if key in data:
                    versions_raw = data[key] if isinstance(data[key], list) else [data[key]]
                    break

            # 尝试从 versions 中提取 content 和 resource
            if versions_raw and isinstance(versions_raw, list) and len(versions_raw) > 0:
                latest = versions_raw[-1] if isinstance(versions_raw[-1], dict) else {}
                raw_content = latest.get("content", "")
                raw_resource = latest.get("resource", {})

                # 构造 parsed versions
                parsed_versions = []
                for v in versions_raw:
                    if isinstance(v, dict):
                        parsed_versions.append(SkillVersionInfo(
                            version=v.get("version", ""),
                            status=v.get("status", ""),
                            create_time=v.get("createTime", 0),
                            update_time=v.get("updateTime", 0),
                            content=v.get("content", ""),
                            resource=v.get("resource", {}),
                        ))

                resource_parsed: dict[str, SkillResourceFile] = {}
                if isinstance(raw_resource, dict):
                    for k, v in raw_resource.items():
                        if isinstance(v, str):
                            resource_parsed[k] = SkillResourceFile(file_name=k, content=v)
                        elif isinstance(v, dict):
                            resource_parsed[k] = SkillResourceFile(**v)
                        else:
                            resource_parsed[k] = SkillResourceFile(file_name=k, content=str(v))

                return SkillDetail(
                    name=name,
                    namespace_id=params.get("namespaceId", ""),
                    description=data.get("description", ""),
                    versions=parsed_versions,
                    content=raw_content,
                    resource=resource_parsed,
                    status=data.get("status", "offline"),
                )

        return None

    def _parse_skill_version_detail_from_data(self, detail: SkillDetail) -> SkillVersionDetail:
        """从 SkillDetail（Client API 格式）构造 SkillVersionDetail。

        Client API 不带 version 参数时，返回的 data 直接包含 content 和 resource
        字段，而不是嵌套在 versions 列表中。

        从 content 中提取 frontmatter，优先于 description 字段。
        """
        # 从 content 中提取 frontmatter
        frontmatter = _parse_frontmatter(detail.content)

        # 将 SkillDetail 的 content 和 resource 转为 SkillVersionDetail
        resource_data = getattr(detail, 'resource', {})
        # 确保 resource 是 dict[str, SkillResourceFile]
        if isinstance(resource_data, dict):
            parsed_resource: dict[str, Any] = {}
            for k, v in resource_data.items():
                if isinstance(v, SkillResourceFile):
                    parsed_resource[k] = v
                elif isinstance(v, dict):
                    parsed_resource[k] = SkillResourceFile(**v)
                elif isinstance(v, str):
                    parsed_resource[k] = SkillResourceFile(file_name=k, content=v)
                else:
                    parsed_resource[k] = SkillResourceFile(file_name=k, content=str(v))
            resource_data = parsed_resource

        return SkillVersionDetail(
            name=detail.name,
            namespace_id=detail.namespace_id,
            description=detail.description,
            status=detail.status,
            content=detail.content,
            resource=resource_data,
            biz_tags=detail.biz_tags,
            frontmatter=frontmatter,
        )

    def delete_skill(self, name: str, namespace_id: str | None = None) -> bool:
        """删除 Skill（需要 Console API 权限，可能不可用）。"""
        # 删除操作通常需要 Console API，这里标记为暂不支持
        raise NotImplementedError("Skill 删除需要使用 Console API，当前客户端仅提供 Client API")

    # ------------------------------------------------------------------ #
    #  便捷方法 — 获取指令文件（带四级回退）
    # ------------------------------------------------------------------ #

    def get_skill_md(self, name: str, version: str | None = None,
                     namespace_id: str | None = None) -> dict[str, Any] | None:
        """获取 SKILL.md 内容。

        使用四级回退策略：
        1. 带 version 获取
        2. 不带 version 获取
        3. Console API 回退
        4. 返回 None

        Returns:
            {"content": str, "frontmatter": {"name": str, "description": str}} 或 None。
        """
        result = self.get_instruction_file(name, version or "", priority=['SKILL.md'])
        if result:
            content = result[1]
            return {
                "content": content,
                "frontmatter": _parse_frontmatter(content),
            }
        return None

    def get_agents_md(self, name: str, version: str | None = None,
                      namespace_id: str | None = None) -> dict[str, Any] | None:
        """获取 AGENTS.md 内容。

        使用四级回退策略，失败返回 None。

        Returns:
            {"content": str, "frontmatter": {"name": str, "description": str}} 或 None。
        """
        result = self.get_instruction_file(name, version or "", priority=['AGENTS.md'])
        if result:
            content = result[1]
            return {
                "content": content,
                "frontmatter": _parse_frontmatter(content),
            }
        return None

    def get_soul_md(self, name: str, version: str | None = None,
                    namespace_id: str | None = None) -> dict[str, Any] | None:
        """获取 SOUL.md 内容。

        使用四级回退策略，失败返回 None。

        Returns:
            {"content": str, "frontmatter": {"name": str, "description": str}} 或 None。
        """
        result = self.get_instruction_file(name, version or "", priority=['SOUL.md'])
        if result:
            content = result[1]
            return {
                "content": content,
                "frontmatter": _parse_frontmatter(content),
            }
        return None

    def _resolve_resource_content(self, resource: dict, key: str) -> str | None:
        """从资源字典中解析指定 key 的内容。"""
        file_obj = resource.get(key)
        if file_obj is None:
            return None
        if isinstance(file_obj, str):
            return file_obj
        if isinstance(file_obj, dict):
            return file_obj.get('content', str(file_obj))
        if hasattr(file_obj, 'content'):
            return file_obj.content
        return None

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "NacosSkillClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
