# Nacos Skill Client — 测试用例覆盖审查报告

> 审查日期: 2026-04-21  
> 审查人: backend-architect (subagent)  
> 基于文档: test-coverage-plan.md v1.0

---

## 一、总体评价

### 正面评价

1. **测试计划结构清晰**：86 条用例按功能测试（32）、接口测试（28）、边界测试（18）、集成测试（8）四个维度组织，层次分明。ZIP 下载、缓存、Token 重试等核心功能的覆盖标注完整。

2. **ZIP 下载功能覆盖充分**：FT-018 ~ FT-024 共 7 条用例覆盖了指定版本下载、最新版下载、Content-Type、文件大小、中文名称、命名空间参数等关键场景，覆盖了 Nacos 官方 3.4 API (`GET /nacos/v3/client/ai/skills`) 的主要调用路径。

3. **Token 过期重试有覆盖**：API-007（API 端点）、EC-013（边界测试）、IT-005（集成测试）三条用例从不同维度覆盖了 token 过期自动重试机制。

4. **缓存测试实现完善**：test_cache.py 的 25 条实际测试覆盖了缓存读写、中文文件名、manifest 更新、集成客户端等场景，与计划中的 FT-025 ~ FT-032 基本对应。

5. **现有测试全部通过**：55 个测试用例 100% 通过，无失败。

### 主要问题

**计划 86 条用例，实际只有 ~21 个测试函数（55 个 test 用例），差距巨大。** 缺失的核心模块测试：
- **无 `test_client.py`**：`NacosSkillClient` 是整个项目的核心，其 `_request`、`_login`、`download_skill_zip`、`get_instruction_file`（四级回退）等方法完全没有测试覆盖。
- **无 `test_routes.py` / `test_api.py`**：API 路由层（`api/routes.py`）完全未测试，包括 8 个 FastAPI 端点的正常/异常路径。
- **无 `test_exceptions.py`**：异常类的定义和传递逻辑未验证。
- **无 `test_config.py` 中部分关键路径**：环境变量优先级、YAML 合并策略等。

---

## 二、遗漏的场景

### 2.1 Client 层核心方法（完全缺失）

| 缺失点 | 相关用例 | 严重程度 |
|--------|---------|---------|
| `_login` 方法测试 | API-022, API-023 | **高** — 登录是唯一一次带密码的 HTTP 请求 |
| `_request` 的 401 自动重试 | API-007, EC-013, IT-005 | **高** — 86 条计划中有 3 条，但无对应的单元测试实现 |
| `download_skill_zip` 的完整逻辑 | FT-018~FT-024, API-009~018 | **高** — ZIP 下载是本次重构的新增核心功能，无单元测试 |
| `get_instruction_file` 四级回退 | FT-016, FT-017, IT-006~IT-008 | **高** — 四级回退逻辑复杂（Level1→Level2→Level3→Level4），未测试 |
| `_parse_skill_list_result` 兼容两种格式 | 无 | 中 — 需要验证 pageItems 和 page_items 两种字段名的兼容 |
| `_get_skill_detail_with_console_api` 解析逻辑 | IT-008 | 中 — Console API 返回格式解析有多条分支路径 |
| `get_all_skills` 分页 + Console 回退 | 无 | 中 — 分页循环 + Console 回退的完整路径未测 |
| `delete_skill` 抛出 NotImplementedError | 无 | 低 — 但作为 public API 应有测试 |

### 2.2 API 路由层（完全缺失）

| 缺失端点 | 相关用例 | 严重程度 |
|---------|---------|---------|
| `GET /api/v1/skills` | API-001~008 | **高** — 列出 Skills 是最常用的端点 |
| `GET /api/v1/skills/search` | FT-006~008 | **高** — 搜索功能 |
| `GET /api/v1/skills/all` | FT-004~005 | 中 |
| `GET /api/v1/skills/metadata` | FT-009~010 | 中 |
| `GET /api/v1/skills/{name}` | API-019~021 | **高** |
| `GET /api/v1/skills/{name}/versions/{version}` | FT-012 | 中 |
| `GET /api/v1/skills/{name}/md/{version}` | FT-013~015, EC-005 | **高** |
| `GET /api/v1/skills/{name}/agents/{version}` | FT-014 | 中 |
| `GET /api/v1/skills/{name}/zip/{version}` | API-009~014 | **高** — ZIP 下载端点 |
| `GET /api/v1/skills/{name}/zip` | API-015~018 | **高** — 最新版 ZIP 端点 |
| `GET /health` | API-026~027 | **高** — 健康检查 |

### 2.3 边界与异常场景

| 缺失场景 | 相关用例 | 严重程度 |
|---------|---------|---------|
| `requests.RequestException` 在 `_login` 中 | API-023 | **高** |
| `requests.RequestException` 在 `_request` 中 | EC-010, EC-011 | **高** |
| 非 JSON 响应处理 | EC-012 | 中 |
| 403 Forbidden 处理 | EC-014 | 中 |
| 503 Service Unavailable 处理 | EC-015 | 中 |
| DNS 解析失败 | EC-011 | 中 |
| ZIP 空数据返回 | EC-016 | 低 |
| 并发下载同一个 ZIP | EC-018 | 低 |
| `cache.save_skill` 权限不足 | EC-006 | 中 |
| `cache.get_skill_file` 非 UTF-8 编码 | EC-008 | 低 |

### 2.4 集成测试实现缺失

| 缺失 | 相关用例 | 严重程度 |
|------|---------|---------|
| IT-001 完整端到端流程 | IT-001 | **高** |
| IT-002 搜索→下载 | IT-002 | **高** |
| IT-003/IT-004 缓存命中/未命中 | FT-025/FT-026 有实现 | 中 — 部分实现 |
| IT-005 Token 过期重连 | API-007, EC-013 | **高** — 有设计无实现 |
| IT-009 环境变量覆盖 | IT-009 | 中 |
| IT-010 默认配置 | IT-010 | 中 — Config 测试有覆盖默认值 |

---

## 三、需要修改的用例

### 3.1 API-002 / API-003 / API-004：分页参数校验预期不明确

计划中说"返回 422（FastAPI 自动校验）或默认 1"，这是不确定的。审查代码后：

- `page_no: int = 1` 和 `page_size: int = 50` 是路由函数参数，**FastAPI 不会对纯 `int` 参数做范围校验**。
- `ListRequest` Schema 中有 `ge=1, le=200` 校验，但该 Schema 未在当前路由中使用（路由直接用了函数参数）。
- **结论**：API-002~004 的预期结果应该是请求正常处理（FastAPI 不会拒绝），而非返回 422。

**建议修改**：改为验证这些极端参数被 Nacos 接受或 Nacos 返回 422（由 Nacos 处理），而不是期望 FastAPI 拒绝。

### 3.2 API-012：空 Skill 名称

计划中写 `GET /api/v1/skills//zip/1.0.0`，但这是非法 URL。实际上 FastAPI 的路由参数 `{name}` 在路径中不会出现双斜杠，应该测试的是包含 URL 编码的空格或其他非法字符。

**建议修改**：改为测试 `GET /api/v1/skills/%20/zip/1.0.0`（URL 编码空格）或 `GET /api/v1/skills/skill%40test/zip/1.0.0`（含 @ 符号）。

### 3.3 FT-013 / FT-014：指令文件端点的版本参数

代码中端点是 `/api/v1/skills/{name}/md/{version}`，但 `NacosSkillClient.get_skill_md()` 方法的 `version` 参数是可选的（`version: str | None = None`）。路由强制要求 `version` 参数，这可能导致不一致。

**建议**：补充测试用例验证当 `version` 为空字符串时，`get_instruction_file` 的四级回退行为（Level1 跳过 → Level2 online → Level3 Console）。

### 3.4 EC-007：缓存 manifest.json 格式错误

计划说"返回 None，记录警告"。代码中 `get_skill_manifest()` 确实捕获了 `json.JSONDecodeError` 并返回 None。但缺少验证"记录警告"这一行为的测试（日志级别验证）。

---

## 四、建议补充的用例

### 4.1 必须补充（P0）

#### 4.1.1 `test_client.py` — Client 层核心逻辑

```
test_login_success: mock POST /nacos/v1/auth/users/login → 200 with accessToken
test_login_failure: mock POST → 401 → 抛出 NacosAuthError
test_request_success: mock GET → 200 with data → 返回 data
test_request_401_retry: mock 首次 401 → mock _login → mock 第二次 200 → 返回 data
test_request_404_raises: mock 404 → 抛出 NacosNotFoundError
test_request_500_raises: mock 500 → 抛出 NacosAPIError
test_request_network_error: mock requests.RequestException → 抛出 NacosSkillError
test_download_skill_zip_success: mock GET /nacos/v3/client/ai/skills → 200 with zip bytes
test_download_skill_zip_not_found: mock 404 → 抛出 NacosNotFoundError
test_download_skill_zip_unauthorized: mock 401 → 重试 → 200
test_download_skill_zip_other_error: mock 500 → 抛出 NacosAPIError
test_get_instruction_file_level1_success: mock get_skill_version_detail → return content
test_get_instruction_file_level2_success: mock get_skill_detail → return resource content
test_get_instruction_file_level3_console: mock _get_skill_detail_with_console_api → return content
test_get_instruction_file_all_levels_fail: mock 所有级别返回空 → 返回 None
test_get_skill_md_cache_hit: 缓存中存在 → 直接从缓存读取
test_get_skill_md_cache_miss: 缓存不存在 → 从 Nacos 获取
test_get_all_skills_pagination: mock 多页 → 验证自动分页
test_get_all_skills_console_fallback: mock list_skills 返回空 → Console API 回退
```

#### 4.1.2 `test_routes.py` — FastAPI 路由端点

```
test_list_skills_200: TestClient → GET /api/v1/skills → 200
test_list_skills_with_page: TestClient → GET /api/v1/skills?page_no=2 → 200
test_search_skills_200: TestClient → GET /api/v1/skills/search?keyword=翻译 → 200
test_search_skills_no_match: TestClient → GET /api/v1/skills/search?keyword=不存在的skill → 200, total=0
test_get_all_skills_200: TestClient → GET /api/v1/skills/all → 200
test_get_skill_detail_200: TestClient → GET /api/v1/skills/翻译助手 → 200
test_get_skill_detail_404: TestClient → GET /api/v1/skills/not_exist → 404
test_get_skill_md_200: TestClient → GET /api/v1/skills/翻译助手/md/v1 → 200
test_get_skill_md_404: TestClient → GET /api/v1/skills/not_exist/md/v1 → 404
test_get_agents_md_200: TestClient → GET /api/v1/skills/代码生成/agents/v1 → 200
test_download_skill_zip_200: TestClient → GET /api/v1/skills/翻译助手/zip/v1 → 200, application/zip
test_download_skill_zip_404: TestClient → GET /api/v1/skills/not_exist/zip/v1 → 404
test_download_skill_zip_latest_200: TestClient → GET /api/v1/skills/翻译助手/zip → 200
test_download_skill_zip_latest_404: TestClient → GET /api/v1/skills/not_exist/zip → 404
test_health_200: TestClient → GET /health → 200, {"status": "ok", "version": "0.2.0"}
test_metadata_200: TestClient → GET /api/v1/skills/metadata → 200
test_skill_versions_200: TestClient → GET /api/v1/skills/翻译助手/versions/v1 → 200
```

### 4.2 应该补充（P1）

#### 4.2.1 `download_skill_zip` 的 Token 过期重试

```
test_download_skill_zip_token_expired_then_success: mock 首次 401 → mock _login → mock 第二次 200 → 返回 zip bytes
test_download_skill_zip_token_expired_twice: mock 两次 401 → 第三次 200 → 应该能工作（第二次 _request 不再 401）
```

#### 4.2.2 ZIP 下载端点 — Content-Disposition 验证

```
test_download_skill_zip_content_disposition_chinese: mock zip → 验证 Content-Disposition 中中文转义正确
test_download_skill_zip_content_disposition_special_chars: 验证特殊字符被替换为 _
```

#### 4.2.3 `_parse_skill_list_result` 兼容测试

```
test_parse_with_pageItems_key: {"pageItems": [...]}
test_parse_with_page_items_key: {"page_items": [...]}
test_parse_empty_response: {}
test_parse_none_data: None → SkillListResult()
```

### 4.3 可选补充（P2）

- 并发下载测试（EC-018）
- 大文件 ZIP 下载测试（EC-017）
- Console API 多分支解析测试
- 环境变量覆盖测试（IT-009）

---

## 五、优先级评估

### 计划中的优先级标注评估

| 用例范围 | 计划标注 | 审查意见 |
|---------|---------|---------|
| ZIP 下载核心路径（FT-018~019, API-009~010） | P0 ✅ | 准确 |
| Token 重试（API-007, EC-013, IT-005） | P0 ✅ | 准确 — 认证是核心依赖 |
| 四级回退（IT-006~008） | P1~P2 ⚠️ | Level1 成功应为 P0（这是主要路径） |
| ZIP Content-Type/大小（FT-023~024, API-017~018） | P1 ⚠️ | 应为 P0 — ZIP 下载的基本验证 |
| 缓存禁用（FT-031） | P2 | 准确 |
| 并发/大文件（EC-017~018） | P2 | 准确 — 边缘场景 |
| 健康检查（API-026~027） | P0/P1 ⚠️ | P0 应为 P1 — 不阻塞主功能 |

### 整体覆盖率估算

| 模块 | 计划用例数 | 已实现 | 覆盖率 |
|------|----------|-------|-------|
| Cache 层 (FT-025~032) | 8 | 8（test_cache.py） | 100% |
| Config 层 (IT-009~010) | 2 | 3（test_config.py） | ~150%（有额外测试） |
| Model 层 (IT-011~012) | 2 | 11（test_models.py） | ~550%（覆盖了更多模型） |
| Utils 层 | 3 | 7（test_utils.py） | ~230% |
| **Client 层** (FT-018~024, API-022~025, 各种 EC) | **~40** | **0** | **0%** |
| **API 路由层** (API-001~028) | **~28** | **0** | **0%** |
| 集成测试 (IT-001~008) | **8** | **3**（部分） | **~40%** |
| **合计** | **86** | **~21 个函数, 55 个 test** | **~24%** |

---

## 六、总结

### 当前状态

55 个测试全部通过 ✅，主要集中在 **Cache、Config、Models、Utils** 四个基础模块。这些是项目的底层支撑，测试质量不错。

### 核心风险

**`NacosSkillClient`（client.py）和 `api/routes.py` 两个核心模块完全没有测试覆盖。** 这相当于：
- 客户端的登录、认证、重试、ZIP 下载、四级回退逻辑 **无测试验证**
- 8 个 FastAPI 端点的请求/响应路径 **无测试验证**
- Token 过期自动重试逻辑虽然有 3 条计划用例，但 **无实际实现**

### 行动建议

1. **立即**：创建 `test_client.py`，覆盖 `_login`、`_request`、`download_skill_zip`、`get_instruction_file` 四级回退
2. **立即**：创建 `test_routes.py`，覆盖所有 8 个 FastAPI 端点的正常和异常路径
3. **短期**：补充 `test_download_skill_zip` 的 token 过期重试集成测试
4. **中期**：补充 `_parse_skill_list_result` 的字段名兼容测试
5. **长期**：补充并发下载、大文件下载等 P2 场景

---

## 七、测试执行结果

**执行命令**：`python3 -m pytest tests/ -v`  
**执行目录**：`/home/root/.openclaw/workspace/projects/nacos-skill-client/`

### 执行结果

```
collected 55 items
55 passed in 0.04s
```

**结论**：55 个现有测试 **全部通过，无失败**。

### 通过详情

| 测试文件 | 测试数量 | 状态 |
|---------|---------|------|
| test_cache.py | 25 | ✅ 全部通过 |
| test_config.py | 13 | ✅ 全部通过 |
| test_models.py | 11 | ✅ 全部通过 |
| test_utils.py | 6 | ✅ 全部通过 |

### 关键发现

1. **无缺失/失败的测试**：55 个测试全部通过，代码运行稳定。
2. **测试范围有限**：仅覆盖了 Cache、Config、Models、Utils 四个模块，核心的 Client 层和 API 路由层完全没有测试。
3. **ZIP 下载功能**：虽然计划中有 FT-018~FT-024 和 API-009~018 共 15 条用例，但 **实际没有对应的测试文件实现**。
4. **Token 过期重试**：虽然计划中有 API-007、EC-013、IT-005 三条用例，但 **实际没有对应的测试实现**。
