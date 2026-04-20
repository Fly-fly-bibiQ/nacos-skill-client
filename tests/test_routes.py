"""测试 API 路由端点。

覆盖 routes.py 中的所有端点：
- GET /api/v1/skills — 列出 Skills
- GET /api/v1/skills/search — 搜索
- GET /api/v1/skills/all — 获取所有
- GET /api/v1/skills/metadata — 元数据
- GET /api/v1/skills/{name} — 详情
- GET /api/v1/skills/{name}/versions/{version} — 版本详情
- GET /api/v1/skills/{name}/md/{version} — SKILL.md
- GET /api/v1/skills/{name}/agents/{version} — AGENTS.md
- GET /api/v1/skills/{name}/zip/{version} — ZIP 下载
- GET /api/v1/skills/{name}/zip — 最新版 ZIP
- GET /health — 健康检查
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from nacos_skill_client.client import NacosSkillClient
from nacos_skill_client.exceptions import NacosNotFoundError
from nacos_skill_client.models import SkillItem, SkillListResult


SKILL_ITEMS = [
    SkillItem(name="翻译助手", description="翻译文本", enable=True, labels={"category": "nlp"}),
    SkillItem(name="代码生成", description="生成代码", enable=True, labels={"category": "code"}),
    SkillItem(name="天气查询", description="查询天气", enable=True, labels={"category": "search"}),
]


@pytest.fixture
def client():
    """TestClient fixture。"""
    return TestClient(app)


def _make_skill_list_result(count=3):
    """构建 mock SkillListResult。"""
    result = MagicMock()
    result.page_items = SKILL_ITEMS[:count]
    result.total_count = count
    result.page_number = 1
    result.pages_available = 1
    return result


@contextmanager
def _mock_list_skills(mock_client):
    """mock client.list_skills 返回默认数据。"""
    result = _make_skill_list_result()
    with patch.object(NacosSkillClient, 'list_skills', return_value=result):
        with patch.object(NacosSkillClient, '_login', return_value=None):
            yield mock_client


@contextmanager
def _mock_metadata(mock_client):
    """mock client.scan_skills_metadata 返回元数据。"""
    from nacos_skill_client.models import SkillMetadata
    from pathlib import Path
    items = [
        SkillMetadata(name="翻译助手", description="翻译文本", skill_path=Path("nacos://public/翻译助手")),
        SkillMetadata(name="代码生成", description="生成代码", skill_path=Path("nacos://public/代码生成")),
        SkillMetadata(name="天气查询", description="查询天气", skill_path=Path("nacos://public/天气查询")),
    ]
    with patch.object(NacosSkillClient, 'scan_skills_metadata', return_value=items):
        with patch.object(NacosSkillClient, '_login', return_value=None):
            yield mock_client


# ============================================================
#  1. GET /api/v1/skills — 列出 Skills
# ============================================================

class TestListSkills:
    """测试 list_skills 端点。"""

    def test_list_skills_200(self, client):
        """正常列出 Skills → 200。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        assert len(data["items"]) == 3
        assert data["items"][0]["name"] == "翻译助手"

    def test_list_skills_with_params(self, client):
        """带 namespace_id 和 page_no 参数。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills", params={"namespace_id": "my-ns", "page_no": 2, "page_size": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3

    def test_list_skills_default_params(self, client):
        """无参数调用，使用默认 namespace_id=public。"""
        call_kwargs = {}

        def capture_list_skills(namespace_id=None, page_no=1, page_size=20):
            call_kwargs["namespace_id"] = namespace_id
            call_kwargs["page_no"] = page_no
            call_kwargs["page_size"] = page_size
            result = _make_skill_list_result()
            return result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'list_skills', side_effect=capture_list_skills):
                client.get("/api/v1/skills")
        assert call_kwargs["namespace_id"] == "public"
        assert call_kwargs["page_no"] == 1
        assert call_kwargs["page_size"] == 50


# ============================================================
#  2. GET /api/v1/skills/search — 搜索
# ============================================================

class TestSearchSkills:
    """测试 search_skills 端点。"""

    def test_search_skills_200(self, client):
        """搜索匹配 → 200。"""
        items = [SkillItem(name="翻译助手", description="翻译", enable=True, labels={})]

        def capture_search(**kwargs):
            result = MagicMock()
            result.page_items = items
            result.total_count = 1
            result.page_number = 1
            result.pages_available = 1
            return result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'search_skills', side_effect=capture_search):
                resp = client.get("/api/v1/skills/search", params={"keyword": "翻译"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["name"] == "翻译助手"

    def test_search_no_match(self, client):
        """搜索无匹配 → 200, total=0。"""
        def capture_search(**kwargs):
            result = MagicMock()
            result.page_items = []
            result.total_count = 0
            result.page_number = 1
            result.pages_available = 0
            return result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'search_skills', side_effect=capture_search):
                resp = client.get("/api/v1/skills/search", params={"keyword": "不存在的skill_xyz"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["items"] == []


# ============================================================
#  3. GET /api/v1/skills/all — 获取所有
# ============================================================

class TestGetAllSkills:
    """测试 get_all_skills 端点。"""

    def test_get_all_skills_200(self, client):
        """获取所有 Skills → 200。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_all_skills', return_value=SKILL_ITEMS):
                resp = client.get("/api/v1/skills/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        assert len(data["items"]) == 3

    def test_get_all_skills_with_page_size(self, client):
        """指定 page_size 参数。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_all_skills', return_value=SKILL_ITEMS):
                resp = client.get("/api/v1/skills/all", params={"page_size": 50})
        assert resp.status_code == 200


# ============================================================
#  4. GET /api/v1/skills/metadata — 元数据
# ============================================================

class TestGetSkillsMetadata:
    """测试 metadata 端点。"""

    def test_metadata_200(self, client):
        """获取 Skill 元数据 → 200。"""
        with _mock_metadata(None):
            resp = client.get("/api/v1/skills/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        assert len(data["skills"]) == 3
        assert data["skills"][0]["name"] == "翻译助手"


# ============================================================
#  5. GET /api/v1/skills/{name} — 详情
# ============================================================

class TestGetSkillDetail:
    """测试 get_skill_detail 端点。"""

    def test_skill_detail_200(self, client):
        """正常获取详情 → 200。"""
        detail = MagicMock()
        detail.model_dump.return_value = {
            "name": "翻译助手",
            "description": "翻译所有文本",
            "status": "online",
        }

        def mock_detail(name):
            return detail

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_skill_detail', side_effect=mock_detail):
                resp = client.get("/api/v1/skills/翻译助手")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "翻译助手"

    def test_skill_detail_404(self, client):
        """Skill 不存在 → 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'get_skill_detail',
                side_effect=NacosNotFoundError("Skill 不存在: not_exist"),
            ):
                resp = client.get("/api/v1/skills/not_exist")
        assert resp.status_code == 404
        data = resp.json()
        assert "not_exist" in data["detail"].lower() or "不存在" in data["detail"]


# ============================================================
#  6. GET /api/v1/skills/{name}/versions/{version}
# ============================================================

class TestGetSkillVersion:
    """测试版本详情端点。"""

    def test_version_detail_200(self, client):
        """获取版本详情 → 200。"""
        detail = MagicMock()
        detail.model_dump.return_value = {
            "name": "翻译助手",
            "version": "v1.0",
            "status": "online",
        }

        def mock_version(name, version):
            return detail

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_skill_version_detail', side_effect=mock_version):
                resp = client.get("/api/v1/skills/翻译助手/versions/v1.0")
        assert resp.status_code == 200


# ============================================================
#  7. GET /api/v1/skills/{name}/md/{version} — SKILL.md
# ============================================================

class TestGetSkillMd:
    """测试 SKILL.md 端点。"""

    def test_skill_md_200(self, client):
        """正常获取 SKILL.md → 200。"""
        content_result = {"content": "# SKILL.md\n\n内容", "frontmatter": {"name": "翻译助手"}}

        def mock_md(name, version):
            return content_result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_skill_md', side_effect=mock_md):
                resp = client.get("/api/v1/skills/翻译助手/md/v1.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_name"] == "SKILL.md"
        assert "SKILL.md" in data["content"]
        assert data["frontmatter"]["name"] == "翻译助手"

    def test_skill_md_404(self, client):
        """SKILL.md 不存在 → 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'get_skill_md',
                side_effect=NacosNotFoundError("无法获取 翻译助手 v1.0 的 SKILL.md"),
            ):
                resp = client.get("/api/v1/skills/not_exist/md/v1.0")
        assert resp.status_code == 404


# ============================================================
#  8. GET /api/v1/skills/{name}/agents/{version} — AGENTS.md
# ============================================================

class TestGetAgentsMd:
    """测试 AGENTS.md 端点。"""

    def test_agents_md_200(self, client):
        """正常获取 AGENTS.md → 200。"""
        content_result = {"content": "# AGENTS.md\n\n内容", "frontmatter": {"name": "代码生成"}}

        def mock_agents(name, version):
            return content_result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'get_agents_md', side_effect=mock_agents):
                resp = client.get("/api/v1/skills/代码生成/agents/v1.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_name"] == "AGENTS.md"

    def test_agents_md_404(self, client):
        """AGENTS.md 不存在 → 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'get_agents_md',
                side_effect=NacosNotFoundError("无法获取 测试/agents/v1.0 的 AGENTS.md"),
            ):
                resp = client.get("/api/v1/skills/测试/agents/v1.0")
        assert resp.status_code == 404


# ============================================================
#  9. GET /api/v1/skills/{name}/zip/{version} — ZIP 下载
# ============================================================

class TestDownloadSkillZip:
    """测试 ZIP 下载端点。"""

    def test_download_zip_200(self, client):
        """正常下载 ZIP → 200, application/zip。"""
        zip_bytes = b"PK\x03\x04fake zip content"

        def mock_download(name, version, namespace_id=None):
            return zip_bytes

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'download_skill_zip', side_effect=mock_download):
                resp = client.get("/api/v1/skills/翻译助手/zip/v1.0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.content == zip_bytes
        # 中文被替换为 _，所以检查 _ 出现
        cd = resp.headers["content-disposition"]
        assert ".zip" in cd

    def test_download_zip_404(self, client):
        """Skill 不存在 → 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                side_effect=NacosNotFoundError("Skill 不存在: not_exist"),
            ):
                resp = client.get("/api/v1/skills/not_exist/zip/v1.0")
        assert resp.status_code == 404

    def test_download_zip_502(self, client):
        """Nacos API 错误 → 502。"""
        from nacos_skill_client.exceptions import NacosAPIError
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                side_effect=NacosAPIError("下载失败: internal error"),
            ):
                resp = client.get("/api/v1/skills/翻译助手/zip/v1.0")
        assert resp.status_code == 502

    def test_download_zip_content_disposition_special_chars(self, client):
        """特殊字符 Skill 名称 → Content-Disposition 中的安全文件名。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                return_value=b"PKzip",
            ):
                resp = client.get("/api/v1/skills/中文Skill/zip/v1.0")
        assert resp.status_code == 200
        cd = resp.headers["content-disposition"]
        # 中文字符应被替换为 _
        assert "中文Skill" not in cd
        assert "zip" in cd

    def test_download_zip_latest_200(self, client):
        """下载最新版 ZIP → 200。"""
        zip_bytes = b"PK\x03\x04latest zip"

        def mock_download(name, version=None, namespace_id=None):
            return zip_bytes

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'download_skill_zip', side_effect=mock_download):
                resp = client.get("/api/v1/skills/翻译助手/zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert resp.content == zip_bytes
        cd = resp.headers["content-disposition"]
        assert ".zip" in cd

    def test_download_zip_latest_404(self, client):
        """最新版 ZIP — Skill 不存在 → 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                side_effect=NacosNotFoundError("Skill 不存在: not_exist"),
            ):
                resp = client.get("/api/v1/skills/not_exist/zip")
        assert resp.status_code == 404

    def test_download_zip_namespace_id(self, client):
        """namespace_id 参数正确传递。"""
        captured_kwargs = {}

        def capture_download(name, version=None, namespace_id=None):
            captured_kwargs["namespace_id"] = namespace_id
            return b"PKzip"

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'download_skill_zip', side_effect=capture_download):
                resp = client.get("/api/v1/skills/翻译助手/zip/v1.0?namespace_id=my-ns")
        assert resp.status_code == 200
        assert captured_kwargs["namespace_id"] == "my-ns"


# ============================================================
#  10. GET /health — 健康检查
# ============================================================

class TestHealthCheck:
    """测试健康检查端点。"""

    def test_health_200(self, client):
        """健康检查 → 200, {"status": "ok", "version": "0.2.0"}。"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"


# ============================================================
#  11. 全局异常处理
# ============================================================

class TestGlobalExceptionHandler:
    """测试全局异常处理。"""

    def test_nacos_api_error_500(self, client):
        """NacosAPIError 触发 500 响应。"""
        from nacos_skill_client.exceptions import NacosAPIError
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'list_skills',
                side_effect=NacosAPIError("downstream error"),
            ):
                resp = client.get("/api/v1/skills")
        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "downstream error"


# ============================================================
#  12. 边界场景
# ============================================================

class TestEdgeCases:
    """边界场景测试。"""

    def test_list_skills_empty_result(self, client):
        """Nacos 返回 0 个 Skill → 200, total_count=0, items=[]。"""
        def mock_empty(**kwargs):
            result = MagicMock()
            result.page_items = []
            result.total_count = 0
            result.page_number = 1
            result.pages_available = 0
            return result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'list_skills', side_effect=mock_empty):
                resp = client.get("/api/v1/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0
        assert data["items"] == []

    def test_search_skills_empty_keyword(self, client):
        """空关键词搜索 → 等价于 list（返回全部）。"""
        def capture_search(**kwargs):
            result = MagicMock()
            result.page_items = SKILL_ITEMS
            result.total_count = 3
            result.page_number = 1
            result.pages_available = 1
            return result

        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(NacosSkillClient, 'search_skills', side_effect=capture_search):
                resp = client.get("/api/v1/skills/search", params={"keyword": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3


# ============================================================
#  13. API-002/003/004 分页参数（审查修改点）
# ============================================================

class TestPaginationParams:
    """API-002/003/004 审查修改：FastAPI 不会对纯 int 参数做范围校验。

    审查结论：极端参数被 Nacos 接收或由 Nacos 返回 422，而非 FastAPI 拒绝。
    """

    def test_page_no_zero_accepted(self, client):
        """page_no=0 被 FastAPI 接受（不会返回 422）。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills", params={"page_no": 0})
        assert resp.status_code == 200

    def test_page_size_zero_accepted(self, client):
        """page_size=0 被 FastAPI 接受（不会返回 422）。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills", params={"page_size": 0})
        assert resp.status_code == 200

    def test_page_size_large_accepted(self, client):
        """page_size=999 被 FastAPI 接受。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills", params={"page_size": 999})
        assert resp.status_code == 200


# ============================================================
#  14. API-012 审查修改：URL 编码空格测试
# ============================================================

class TestUrlEncodedNames:
    """API-012 审查修改：测试 URL 编码的 Skill 名称。"""

    def test_url_encoded_space(self, client):
        """URL 编码空格 → 应触发 404（Skill 不存在）。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                side_effect=NacosNotFoundError("Skill 不存在: "),
            ):
                resp = client.get("/api/v1/skills/%20/zip/1.0.0")
        assert resp.status_code == 404

    def test_url_encoded_at_symbol(self, client):
        """URL 编码 @ 符号 → 应触发 404。"""
        with patch.object(NacosSkillClient, '_login', return_value=None):
            with patch.object(
                NacosSkillClient, 'download_skill_zip',
                side_effect=NacosNotFoundError("Skill 不存在: skill@test"),
            ):
                resp = client.get("/api/v1/skills/skill%40test/zip/1.0.0")
        assert resp.status_code == 404


# ============================================================
#  15. 请求验证
# ============================================================

class TestValidation:
    """请求参数验证。"""

    def test_list_skills_accepts_any_int(self, client):
        """list_skills 路由使用 int 参数，接受任意整数值。"""
        with _mock_list_skills(None):
            resp = client.get("/api/v1/skills", params={"page_no": -1, "page_size": -5})
        assert resp.status_code == 200
