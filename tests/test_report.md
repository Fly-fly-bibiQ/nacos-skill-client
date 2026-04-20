# Nacos Skill Client — 修复报告

## 修复日期
2026-04-20

## Bug 1：版本 online 限制导致 get_skill_version_detail() 失败

### 问题描述
Nacos Client API `/v3/client/ai/agentspecs` 在请求指定 version 时，如果版本不是 online 状态，会返回 "version not online" 错误。同时不带 version 参数时返回的 data 结构里没有 `versions` 字段，只有 `content` 和 `resource` 字段。

### 修复内容

**nacos_skill_client/models.py**
- `SkillDetail` 新增 `content: str` 和 `resource` 字段，支持 Client API 不带 version 参数时的返回格式
- `SkillVersionDetail` 新增 `scope`、`enable`、`from_source`、`labels`、`editing_version`、`versions` 字段，支持回退格式

**nacos_skill_client/client.py**
- `get_skill_version_detail()`：先尝试带 version 参数调用 API，失败后回退到不带 version 的请求，通过 `_parse_skill_version_detail_from_data()` 从返回数据的 content/resource 字段构造 SkillVersionDetail
- `get_skill_md()` / `get_agents_md()` / `get_soul_md()`：使用 `get_skill_version_detail()`（已含回退逻辑），失败时抛出明确的 NacosNotFoundError
- `get_instruction_file()`：如果指定 version 获取失败，回退到不带 version 获取 SkillDetail，然后从 resource 字段提取指令文件
- 新增 `_resolve_resource_content()`：统一从资源字典中解析文件内容
- 移除旧的 `_extract_file_content()` 方法

## Bug 2：FastAPI 异常处理

### 问题描述
调用不存在的 Skill 时返回 500 而不是 404，暴露了内部异常堆栈信息。

### 修复内容

**api/main.py**
- 添加 `NacosNotFoundError` → HTTP 404 全局异常处理器
- 添加 `NacosAuthError` → HTTP 401 全局异常处理器
- 添加 `NacosAPIError` → HTTP 500 全局异常处理器
- 添加 `RequestValidationError` → HTTP 422 全局异常处理器（FastAPI 内置验证错误）
- 添加通用 `Exception` → HTTP 500 全局异常处理器（记录日志，返回通用错误信息，不暴露堆栈）

## 验证结果

- ✅ `python3 -c "from api.main import app; print('OK')"` — 导入成功
- ✅ 全部 29 个单元测试通过
- ✅ 无服务正在运行

## 修改文件清单

| 文件 | 变更类型 |
|------|---------|
| `nacos_skill_client/models.py` | 新增字段（content, resource, scope, enable 等） |
| `nacos_skill_client/client.py` | 版本回退逻辑、新方法、重构 |
| `api/main.py` | 全局异常处理器 |
