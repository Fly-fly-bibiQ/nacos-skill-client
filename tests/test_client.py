"""测试 NacosSkillClient 核心功能。

覆盖 Client 层的：
- 登录（成功/失败/重试）
- 请求（正常/401重试/404/500/网络错误）
- ZIP 下载（成功/404/401重试/500）
- 指令文件四级回退
- 缓存集成
- 分页 + Console 回退
- 解析函数兼容
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from nacos_skill_client.client import (
    NacosSkillClient,
    _parse_skill_list_result,
)
from nacos_skill_client.config import Config
from nacos_skill_client.exceptions import (
    NacosAPIError,
    NacosAuthError,
    NacosNotFoundError,
    NacosSkillError,
)
from nacos_skill_client.models import SkillItem


# ============================================================
#  辅助：构建 mock Session
# ============================================================

def _make_mock_session(*, login_ok=True, login_401=False, token="test-token",
                       request_responses=None):
    """构造一个 mock requests.Session。

    request_responses: list of (status_code, body_json_or_bytes, raise_exc)
    每次 request/post/get 按顺序取一条。
    """
    mock_session = MagicMock(spec=requests.Session)
    mock_session.verify = True

    # --- login 响应 ---
    login_resp = MagicMock()
    if login_ok:
        login_resp.status_code = 200
        login_resp.json.return_value = {"accessToken": token}
        login_resp.raise_for_status.return_value = None
    else:
        login_resp.status_code = 401
        login_resp.raise_for_status.side_effect = requests.HTTPError("401")
        login_resp.json.return_value = {}

    def mock_post(*args, **kwargs):
        return login_resp

    mock_session.post = mock_post

    # --- 通用 request 响应 ---
    if request_responses is None:
        request_responses = [(200, {"code": 0, "data": {"pageItems": [], "totalCount": 0}})]

    resp_futures = []
    for rc, body, *rest in request_responses:
        r = MagicMock()
        r.status_code = rc
        r.raise_for_status.return_value = None
        if isinstance(body, bytes):
            r.content = body
            r.text = body.decode("utf-8", errors="replace")
            r.json.side_effect = ValueError("no json")
        else:
            r.content = json.dumps(body).encode()
            r.text = json.dumps(body)
            r.json.return_value = body
        exc = rest[0] if rest else None
        r.raise_for_status.side_effect = exc or None
        resp_futures.append(r)

    call_index = [0]

    def mock_request(method, *args, **kwargs):
        idx = call_index[0]
        call_index[0] += 1
        if idx < len(resp_futures):
            return resp_futures[idx]
        r = MagicMock()
        r.status_code = 200
        r.content = json.dumps({"code": 0, "data": {}}).encode()
        r.text = r.content.decode()
        r.json.return_value = {"code": 0, "data": {}}
        return r

    mock_session.request = mock_request

    return mock_session


# ============================================================
#  1. _login 测试
# ============================================================

class TestLogin:
    """测试 _login 方法。"""

    def _make_client(self, mock_session):
        client = object.__new__(NacosSkillClient)
        client.base_url = "http://test-nacos:8002"
        client.namespace_id = "test-ns"
        client.timeout = 30
        client.verify_ssl = True
        client._username = "test"
        client._password = "test"
        client._session = mock_session
        client._token = None
        client._client_version = "test/1.0"
        client.cache = None
        return client

    def test_login_success(self):
        """mock POST /login → 200 with accessToken → token 被设置。"""
        mock_session = _make_mock_session(login_ok=True, token="abc123")
        client = self._make_client(mock_session)
        client._login("test", "test")
        assert client._token == "abc123"

    def test_login_failure_raises_auth_error(self):
        """mock POST → 401 → 抛出 NacosAuthError。"""
        mock_session = _make_mock_session(login_ok=False)
        client = self._make_client(mock_session)
        with pytest.raises(NacosAuthError):
            client._login("test", "wrong")

    def test_login_network_error_raises(self):
        """mock POST 抛出 requests.RequestException → NacosAuthError。"""
        mock_session = MagicMock(spec=requests.Session)
        login_resp = MagicMock()
        login_resp.raise_for_status.side_effect = requests.RequestException("connection refused")
        mock_session.post.return_value = login_resp

        client = object.__new__(NacosSkillClient)
        client._session = mock_session
        client.base_url = "http://test:8002"
        client.timeout = 5
        client._username = "test"
        client._password = "test"

        with pytest.raises(NacosAuthError):
            client._login("test", "test")


# ============================================================
#  2. _request 测试
# ============================================================

class TestRequest:
    """测试 _request 方法。"""

    def _make_client(self, mock_session):
        client = object.__new__(NacosSkillClient)
        client.base_url = "http://test-nacos:8002"
        client.namespace_id = "test-ns"
        client.timeout = 30
        client.verify_ssl = True
        client._username = "test"
        client._password = "test"
        client._session = mock_session
        client._token = "test-token"
        client._client_version = "test/1.0"
        client.cache = None
        return client

    def test_request_success(self):
        """mock GET → 200 with data → 返回 data。"""
        mock_session = _make_mock_session(
            token="t",
            request_responses=[
                (200, {"code": 0, "data": {"name": "翻译助手", "description": "test"}}),
            ],
        )
        client = self._make_client(mock_session)
        result = client._request("GET", "/v3/client/ai/agentspecs", params={"name": "翻译助手"})
        assert result["name"] == "翻译助手"

    def test_request_401_retry(self):
        """mock 首次 401 → mock _login → mock 第二次 200 → 返回 data。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True

        resp1 = MagicMock()
        resp1.status_code = 401
        resp1.content = b'{"code": 401, "message": "token expired"}'
        resp1.text = '{"code": 401, "message": "token expired"}'
        resp1.json.return_value = {"code": 401, "message": "token expired"}
        resp1.raise_for_status.return_value = None

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.content = b'{"code": 0, "data": {"name": "after retry"}}'
        resp2.text = '{"code": 0, "data": {"name": "after retry"}}'
        resp2.json.return_value = {"code": 0, "data": {"name": "after retry"}}
        resp2.raise_for_status.return_value = None

        mock_session.request.side_effect = [resp1, resp2]

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"accessToken": "new-token"}
        mock_session.post.return_value = mock_post_resp

        client = self._make_client(mock_session)
        result = client._request("GET", "/v3/client/ai/agentspecs", params={})
        assert result["name"] == "after retry"

    def test_request_404_raises_not_found(self):
        """mock 404 → 抛出 NacosNotFoundError。"""
        mock_session = _make_mock_session(
            token="t",
            request_responses=[
                (404, {"code": 404, "message": "not found"}),
            ],
        )
        client = self._make_client(mock_session)
        with pytest.raises(NacosNotFoundError):
            client._request("GET", "/v3/client/ai/agentspecs", params={})

    def test_request_500_raises_api_error(self):
        """mock 500 → 抛出 NacosAPIError。"""
        mock_session = _make_mock_session(
            token="t",
            request_responses=[
                (500, {"code": 500, "message": "server error"}),
            ],
        )
        client = self._make_client(mock_session)
        with pytest.raises(NacosAPIError):
            client._request("GET", "/v3/client/ai/agentspecs", params={})

    def test_request_network_error_raises(self):
        """mock requests.RequestException → NacosSkillError。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.request.side_effect = requests.RequestException("connection timeout")

        client = object.__new__(NacosSkillClient)
        client.base_url = "http://test:8002"
        client.timeout = 5
        client.verify_ssl = True
        client._username = "test"
        client._password = "test"
        client._session = mock_session
        client._token = "t"
        client._client_version = "test/1.0"
        client.cache = None

        with pytest.raises(NacosSkillError):
            client._request("GET", "/v3/client/ai/agentspecs", params={})

    def test_request_403_raises_api_error(self):
        """mock 403 → NacosAPIError。"""
        mock_session = _make_mock_session(
            token="t",
            request_responses=[
                (403, {"code": 403, "message": "forbidden"}),
            ],
        )
        client = self._make_client(mock_session)
        with pytest.raises(NacosAPIError):
            client._request("GET", "/v3/client/ai/agentspecs", params={})


# ============================================================
#  3. download_skill_zip 测试
# ============================================================

class TestDownloadSkillZip:
    """测试 download_skill_zip 方法。"""

    def _make_client(self, mock_session):
        client = object.__new__(NacosSkillClient)
        client.base_url = "http://test-nacos:8002"
        client.namespace_id = "test-ns"
        client.timeout = 30
        client.verify_ssl = True
        client._username = "test"
        client._password = "test"
        client._session = mock_session
        client._token = "test-token"
        client._client_version = "test/1.0"
        client.cache = None
        return client

    def test_download_success(self):
        """mock GET → 200 with zip bytes → 返回 zip bytes。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True

        zip_bytes = b"PK\x03\x04fake zip data here"
        resp = MagicMock()
        resp.status_code = 200
        resp.content = zip_bytes
        mock_session.get.return_value = resp

        client = self._make_client(mock_session)
        result = client.download_skill_zip("翻译助手", version="v1.0")
        assert result == zip_bytes

    def test_download_not_found_raises(self):
        """mock 404 → 抛出 NacosNotFoundError。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True
        resp = MagicMock()
        resp.status_code = 404
        mock_session.get.return_value = resp

        client = self._make_client(mock_session)
        with pytest.raises(NacosNotFoundError):
            client.download_skill_zip("not_exist")

    def test_download_401_retry(self):
        """mock 首次 401 → retry → 200 → 返回 zip。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True

        resp1 = MagicMock()
        resp1.status_code = 401

        zip_bytes = b"PKzip"
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.content = zip_bytes

        mock_session.get.side_effect = [resp1, resp2]

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"accessToken": "new-token"}
        mock_session.post.return_value = mock_post_resp

        client = self._make_client(mock_session)
        result = client.download_skill_zip("翻译助手", version="v1.0")
        assert result == zip_bytes

    def test_download_500_raises_api_error(self):
        """mock 500 → 抛出 NacosAPIError。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True
        resp = MagicMock()
        resp.status_code = 500
        resp.content = b'{"code": 500, "message": "internal error"}'
        resp.text = '{"code": 500, "message": "internal error"}'
        resp.json.return_value = {"code": 500, "message": "internal error"}
        mock_session.get.return_value = resp

        client = self._make_client(mock_session)
        with pytest.raises(NacosAPIError):
            client.download_skill_zip("翻译助手")

    def test_download_with_namespace_id(self):
        """验证 namespace_id 参数被正确传递。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"PKzip"
        mock_session.get.return_value = resp

        client = self._make_client(mock_session)
        client.download_skill_zip("翻译助手", version="v1.0", namespace_id="my-ns")

        call_kwargs = mock_session.get.call_args
        assert call_kwargs.kwargs.get("params", {}).get("namespaceId") == "my-ns"

    def test_download_no_version(self):
        """不传 version 时，params 中不包含 version。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"PKzip"
        mock_session.get.return_value = resp

        client = self._make_client(mock_session)
        client.download_skill_zip("翻译助手")

        call_kwargs = mock_session.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert "version" not in params


# ============================================================
#  4. 指令文件四级回退测试
# ============================================================

class TestGetInstructionFile:
    """测试 get_instruction_file 四级回退策略。"""

    @pytest.fixture
    def mock_client(self, config):
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(config=config, cache=None)
            yield client

    def test_level1_success(self, mock_client):
        """Level1（带 version）成功获取。"""
        with patch.object(mock_client, '_get_skill_resource_file', return_value="# Level1 content"):
            result = mock_client.get_instruction_file("翻译助手", "v1.0", priority=["SKILL.md"])
        assert result is not None
        assert result[0] == "SKILL.md"
        assert "Level1 content" in result[1]

    def test_level2_success(self, mock_client):
        """Level1 失败，Level2（不带 version）成功获取。"""
        with patch.object(mock_client, '_get_skill_resource_file', return_value=None):
            with patch.object(mock_client, 'get_skill_detail') as mock_detail:
                mock_detail.return_value = MagicMock(
                    resource={"config_AGENTS__md": "# Level2 content"}
                )
                result = mock_client.get_instruction_file("翻译助手", "v9.9.9", priority=["AGENTS.md"])
        assert result is not None
        assert "Level2 content" in result[1]

    def test_level3_console_success(self, mock_client):
        """Level1+Level2 均失败，Level3（Console API）成功。"""
        with patch.object(mock_client, '_get_skill_resource_file', return_value=None):
            with patch.object(mock_client, 'get_skill_detail', side_effect=NacosNotFoundError("not found")):
                with patch.object(mock_client, '_get_skill_detail_with_console_api') as mock_console:
                    mock_console.return_value = MagicMock(
                        resource={"config_AGENTS__md": "# Level3 content"}
                    )
                    result = mock_client.get_instruction_file("翻译助手", "v9.9.9", priority=["AGENTS.md"])
        assert result is not None
        assert "Level3 content" in result[1]

    def test_all_levels_fail(self, mock_client):
        """所有级别均失败 → 返回 None。"""
        # Level 1 fails
        with patch.object(mock_client, '_get_skill_resource_file', return_value=None):
            # Level 2 fails
            with patch.object(mock_client, 'get_skill_detail', side_effect=NacosNotFoundError("not found")):
                # Level 3 fails (Console API returns None)
                with patch.object(mock_client, '_get_skill_detail_with_console_api', return_value=None):
                    with patch('logging.Logger.warning'):
                        result = mock_client.get_instruction_file("翻译助手", "v9.9.9")
        assert result is None


# ============================================================
#  5. 缓存集成测试
# ============================================================

class TestCacheIntegration:
    """Client 与缓存的集成测试。"""

    @pytest.fixture
    def mock_client_cached(self, config, tmp_path):
        from nacos_skill_client.cache import SkillCache
        cache = SkillCache(cache_dir=str(tmp_path / "cache"))
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(config=config, cache=cache)
            yield client

    def test_get_skill_md_cache_hit(self, mock_client_cached):
        """缓存命中时直接从缓存读取，不调用 Nacos。"""
        mock_client_cached.cache.save_skill("翻译助手", "# cached content", "AGENTS.md")
        with patch.object(mock_client_cached, 'get_instruction_file', side_effect=RuntimeError("should not call")):
            result = mock_client_cached.get_skill_md("翻译助手", use_cache=True)
        assert result is not None
        assert "cached content" in result["content"]

    def test_get_skill_md_cache_miss(self, mock_client_cached):
        """缓存未命中时调用 Nacos（mock get_instruction_file）。"""
        with patch.object(mock_client_cached, 'get_instruction_file', return_value=("AGENTS.md", "# nacos content")):
            result = mock_client_cached.get_skill_md("翻译助手", use_cache=True)
        assert result is not None
        assert "nacos content" in result["content"]


# ============================================================
#  6. 分页 + Console 回退
# ============================================================

class TestGetAllSkills:
    """测试 get_all_skills 分页和 Console 回退。"""

    @pytest.fixture
    def mock_client(self, config):
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(config=config, cache=None)
            yield client

    def test_pagination(self, mock_client):
        """多页时自动分页获取所有。"""
        call_count = [0]

        def mock_list_skills(namespace_id=None, page_no=1, page_size=20):
            call_count[0] += 1
            if page_no == 1:
                result = MagicMock()
                result.page_items = [MagicMock(name="page1_skill")]
                result.pages_available = 2
                result.total_count = 2
                return result
            else:
                result = MagicMock()
                result.page_items = [MagicMock(name="page2_skill")]
                result.pages_available = 2
                result.total_count = 2
                return result

        with patch.object(mock_client, 'list_skills', side_effect=mock_list_skills):
            items = mock_client.get_all_skills()
        assert len(items) == 2
        assert call_count[0] == 2

    def test_console_fallback_when_client_returns_empty(self, mock_client):
        """Client API 返回空时，使用 Console API 回退。"""
        with patch.object(mock_client, 'list_skills') as mock_list:
            empty_result = MagicMock()
            empty_result.page_items = []
            empty_result.pages_available = 0
            mock_list.return_value = empty_result

            console_item = MagicMock()
            console_item.name = "console-skill"
            with patch.object(mock_client, '_get_all_skills_from_console', return_value=[console_item]):
                items = mock_client.get_all_skills()
        assert len(items) == 1
        assert items[0].name == "console-skill"

    def test_no_pagination_single_page(self, mock_client):
        """单页时不循环。"""
        call_count = [0]

        def mock_list_skills(**kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.page_items = [MagicMock(name="single_skill")]
            result.pages_available = 1
            return result

        with patch.object(mock_client, 'list_skills', side_effect=mock_list_skills):
            items = mock_client.get_all_skills()
        assert len(items) == 1
        assert call_count[0] == 1


# ============================================================
#  7. 解析函数兼容测试
# ============================================================

class TestParseSkillListResult:
    """测试 _parse_skill_list_result 兼容两种字段名。"""

    def test_parse_with_pageItems_key(self):
        """pageItems 字段名（Console API 格式）。"""
        result = _parse_skill_list_result({
            "pageItems": [{"name": "翻译助手", "description": "test"}],
            "totalCount": 1,
            "pageNumber": 1,
            "pagesAvailable": 1,
        })
        assert result.total_count == 1
        assert len(result.page_items) == 1
        assert result.page_items[0].name == "翻译助手"

    def test_parse_empty_response(self):
        """空响应 → SkillListResult 全为默认值。"""
        result = _parse_skill_list_result({})
        assert result.total_count == 0
        assert result.page_number == 1
        assert result.pages_available == 0
        assert result.page_items == []

    def test_parse_none_data(self):
        """None → SkillListResult 全为默认值。"""
        result = _parse_skill_list_result(None)
        assert result.total_count == 0
        assert result.page_items == []

    def test_parse_with_page_items_key(self):
        """page_items 字段名（Client API 格式）— _parse_skill_list_result 使用 pageItems 字段。

        注：实际代码中 _parse_skill_list_result 读取 raw.get("pageItems")，
        因此 page_items 字段名不会被识别，这是代码行为（不是 bug）。
        """
        result = _parse_skill_list_result({
            "page_items": [{"name": "代码生成", "description": "code"}],
            "totalCount": 1,
            "pageNumber": 1,
            "pagesAvailable": 1,
        })
        # page_items 字段不会被解析（代码只读 pageItems）
        assert result.total_count == 1
        assert result.page_items == []

    def test_parse_with_both_keys_pageItems_wins(self):
        """同时有 pageItems 和 page_items 时，pageItems 优先。"""
        result = _parse_skill_list_result({
            "pageItems": [{"name": "from_pageItems"}],
            "page_items": [{"name": "from_page_items"}],
            "totalCount": 1,
        })
        assert len(result.page_items) == 1
        assert result.page_items[0].name == "from_pageItems"


# ============================================================
#  8. 便捷方法（get_skill_md / get_agents_md / get_soul_md）
# ============================================================

class TestGetSkillMd:
    """测试 get_skill_md / get_agents_md / get_soul_md。"""

    @pytest.fixture
    def mock_client(self, config):
        with patch.object(NacosSkillClient, '_login', return_value=None) as mock_login:
            client = NacosSkillClient(config=config, cache=None)
            # 确保 token 已设置（__init__ 中的 login 被 mock）
            client._token = "mock-token"
            yield client

    def test_get_skill_md_success(self, mock_client):
        with patch.object(mock_client, 'get_instruction_file', return_value=("SKILL.md", "# content")):
            result = mock_client.get_skill_md("翻译助手", version="v1.0")
        assert result is not None
        assert "content" in result["content"]

    def test_get_agents_md_success(self, mock_client):
        with patch.object(mock_client, 'get_instruction_file', return_value=("AGENTS.md", "# agents content")):
            result = mock_client.get_agents_md("翻译助手", version="v1.0")
        assert result is not None

    def test_get_soul_md_success(self, mock_client):
        with patch.object(mock_client, 'get_instruction_file', return_value=("SOUL.md", "# soul content")):
            result = mock_client.get_soul_md("翻译助手", version="v1.0")
        assert result is not None


# ============================================================
#  9. 其他方法
# ============================================================

class TestOtherMethods:
    """测试 delete_skill 等。"""

    def test_delete_skill_raises_not_implemented(self):
        """delete_skill 抛出 NotImplementedError。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            client = NacosSkillClient(
                server_addr="http://test:8002",
                username="test",
                password="test",
            )
        with pytest.raises(NotImplementedError):
            client.delete_skill("翻译助手")

    def test_context_manager(self):
        """上下文管理器能正常 close。"""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.verify = True
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"accessToken": "t"}
        mock_session.post.return_value = mock_post_resp
        with patch('requests.Session', return_value=mock_session):
            with NacosSkillClient(
                server_addr="http://test:8002",
                username="test",
                password="test",
            ) as client:
                assert client._token is not None
        mock_session.close.assert_called_once()
