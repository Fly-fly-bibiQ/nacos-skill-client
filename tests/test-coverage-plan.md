# Nacos Skill Client — 测试用例覆盖计划

> 文档版本: v1.0  
> 创建日期: 2026-04-21  
> 项目版本: 0.2.0  
> 基于 FastAPI 重构后的 Nacos Skill 管理客户端

---

## 一、测试范围总览

| 维度 | 覆盖内容 | 用例数量 |
|------|---------|---------|
| 功能测试 | Skill 列表/详情/搜索、ZIP 下载、缓存 | 32 |
| 接口测试 | 5 组 API 端点的正常/异常路径 | 28 |
| 边界测试 | 不存在的 Skill、版本不存在、token 过期、网络超时等 | 18 |
| 集成测试 | 完整请求流程（登录→下载→缓存→解压验证） | 8 |
| **合计** | | **86** |

---

## 二、功能测试（Functional Tests）

### 2.1 Skill 列表与元数据

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **FT-001** | 列出所有 Skills（默认分页） | Nacos 服务可达 | `GET /api/v1/skills` | 返回 2xx，包含 `total_count`、`page_number`、`pages_available`、`items` 数组 | P0 |
| **FT-002** | 列出 Skills 指定页码 | Nacos 有多个分页 | `GET /api/v1/skills?page_no=2&page_size=10` | 返回第 2 页数据，`page_number=2` | P0 |
| **FT-003** | 列出 Skills 指定 page_size | Nacos 有多个分页 | `GET /api/v1/skills?page_size=5` | 每页返回不超过 5 条 | P1 |
| **FT-004** | 获取所有 Skills（不分页） | Nacos 有 Skills | `GET /api/v1/skills/all` | 返回所有 Skills，`total_count` 为总数量 | P0 |
| **FT-005** | 获取所有 Skills 指定 page_size | Nacos 有 Skills | `GET /api/v1/skills/all?page_size=50` | `total_count` 不变，`items` 数量 = min(总数量, 50) | P1 |
| **FT-006** | 搜索 Skills（关键词匹配） | Nacos 有 Skills | `GET /api/v1/skills/search?keyword=翻译&page_size=5` | 返回包含"翻译"关键词的 Skills | P0 |
| **FT-007** | 搜索 Skills（无匹配结果） | Nacos 无匹配 Skill | `GET /api/v1/skills/search?keyword=不存在的skill_xyz` | 返回 `total_count=0`，`items` 为空数组 | P0 |
| **FT-008** | 搜索 Skills（空关键词） | Nacos 有 Skills | `GET /api/v1/skills/search?keyword=&page_no=1&page_size=10` | 返回第 1 页全部 Skills（等价于 list） | P1 |
| **FT-009** | 获取 Skill 元数据（Level 1） | Nacos 有 Skills | `GET /api/v1/skills/metadata` | 返回 `total_count` 和 `skills` 数组，每项含 `name` + `description` | P0 |
| **FT-010** | 获取 Skill 元数据指定命名空间 | Nacos 有多个命名空间 | `GET /api/v1/skills/metadata?namespace_id=custom-ns` | 返回指定命名空间的 Skill 元数据 | P1 |

### 2.2 Skill 详情

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **FT-011** | 获取 Skill 详情 | Nacos 有指定 Skill | `GET /api/v1/skills/{skill_name}` | 返回 2xx，包含 `name`、`description`、`status`、`resource` 等字段 | P0 |
| **FT-012** | 获取 Skill 版本详情 | Nacos Skill 有多个版本 | `GET /api/v1/skills/{skill_name}/versions/{version}` | 返回指定版本的详情 | P0 |
| **FT-013** | 获取 SKILL.md | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/md/{version}` | 返回包含 `file_name`、`content`、`frontmatter` 的 JSON | P0 |
| **FT-014** | 获取 AGENTS.md | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/agents/{version}` | 返回包含 `file_name`、`content`、`frontmatter` 的 JSON | P0 |
| **FT-015** | SKILL.md 包含 frontmatter | Nacos Skill 有 frontmatter | `GET /api/v1/skills/{skill_name}/md/{version}` | `frontmatter` 字典中包含 `name`、`description` 键 | P1 |
| **FT-016** | 指令文件四级回退 — Level1 带 version | Nacos Skill 指定版本存在 | `GET /api/v1/skills/{skill_name}/md/{version}` | 返回指定版本的文件内容 | P1 |
| **FT-017** | 指令文件四级回退 — Level2 不带 version | Nacos Skill online | `GET /api/v1/skills/{skill_name}/md/{version}` | 从 online 版本获取文件内容 | P2 |

### 2.3 ZIP 下载（重构新增核心功能）

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **FT-018** | 下载指定版本 Skill ZIP | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/zip/{version}` | 返回 200，Content-Type=`application/zip`，`Content-Disposition` 含文件名 | P0 |
| **FT-019** | 下载最新版本 Skill ZIP | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/zip` | 返回 200，ZIP 数据有效（可解压），filename 为 `{safe_name}.zip` | P0 |
| **FT-020** | 下载 Skill ZIP 并解压验证 | Nacos Skill 存在 | 下载 ZIP → 用 `zipfile` 解压 | 解压后的文件列表包含 `AGENTS.md`、`SOUL.md` 等 Skill 资源文件 | P0 |
| **FT-021** | 下载 Skill ZIP 含中文名称 | Nacos Skill 名称含中文 | `GET /api/v1/skills/翻译助手/zip/{version}` | 文件名中的中文被安全转义为 `_` 下划线，ZIP 可正常下载 | P1 |
| **FT-022** | 下载 Skill ZIP 使用命名空间参数 | Nacos 有指定命名空间的 Skill | `GET /api/v1/skills/{skill_name}/zip/{version}?namespace_id=custom-ns` | 从指定命名空间下载 ZIP | P2 |
| **FT-023** | ZIP 下载 Content-Type 正确 | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/zip/{version}` | 检查 `Content-Type` 头 = `application/zip` | P1 |
| **FT-024** | ZIP 下载文件大小 > 0 | Nacos Skill 存在 | `GET /api/v1/skills/{skill_name}/zip/{version}` | 返回的字节数 > 0 | P1 |

### 2.4 缓存功能

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **FT-025** | 缓存命中 — 从缓存读取 SKILL.md | 缓存目录中存在 Skill 文件 | `client.get_skill_md(name, use_cache=True)` | 直接从磁盘读取，不调用 Nacos API | P0 |
| **FT-026** | 缓存未命中 — 从 Nacos 下载 | 缓存目录中不存在该 Skill | `client.get_skill_md(name, use_cache=True)` | 先从 Nacos 获取，写入缓存，返回内容 | P0 |
| **FT-027** | 缓存目录不存在时自动创建 | 缓存未初始化 | 调用 `SkillCache(name)` 并 `save_skill` | `.skill_cache/{safe_name}/` 目录及 `AGENTS.md`、`manifest.json` 被创建 | P0 |
| **FT-028** | 缓存 manifest.json 包含元数据 | 缓存写入完成 | 读取缓存目录下的 `manifest.json` | 包含 `name`、`version`、`description`、`download_time` 字段 | P1 |
| **FT-029** | 缓存安全文件名 — 非 ASCII 字符 | Skill 名称含中文/特殊字符 | 缓存"翻译助手" | 目录名为 hex 编码的安全文件名 | P1 |
| **FT-030** | 缓存读取失败 — 文件损坏 | 缓存文件存在但损坏 | `cache.get_skill_file(name, filename)` | 返回 `(None, None)`，不抛出异常 | P1 |
| **FT-031** | 缓存未启用 — 跳过缓存 | `config.cache.enabled=False` | `client.get_skill_md(name, use_cache=True)` | 仍从 Nacos 获取，不访问本地缓存 | P2 |
| **FT-032** | 获取所有已缓存的 Skill | 缓存目录中有多个 Skill | `cache.get_all_cached_skills()` | 返回已缓存的 Skill 名称列表 | P1 |

---

## 三、接口测试（API Endpoint Tests）

### 3.1 `GET /api/v1/skills` — 列出 Skills

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-001** | 正常列出 Skills | Nacos 服务正常 | `GET /api/v1/skills` | 200，JSON 包含 `total_count`、`items` | P0 |
| **API-002** | 无效 page_no（< 1） | 无 | `GET /api/v1/skills?page_no=0` | 返回 422（FastAPI 自动校验）或默认 1 | P1 |
| **API-003** | 无效 page_size（< 1） | 无 | `GET /api/v1/skills?page_size=0` | 返回 422 或默认 1 | P1 |
| **API-004** | 无效 page_size（> 200） | 无 | `GET /api/v1/skills?page_size=999` | 返回 422 或截断至 200 | P1 |
| **API-005** | 无效 namespace_id | 无 | `GET /api/v1/skills?namespace_id=` | Nacos 返回对应结果（空或默认命名空间） | P2 |
| **API-006** | Nacos 服务不可达 | Nacos 下线 | `GET /api/v1/skills` | 返回 500 或 502，包含错误详情 | P0 |
| **API-007** | Nacos token 过期 | Token 即将过期 | `GET /api/v1/skills` | 自动重新登录，返回 200 | P0 |
| **API-008** | 无参数调用 | 无 | `GET /api/v1/skills` | 使用默认 `namespace_id=public`、`page_no=1`、`page_size=50` | P1 |

### 3.2 `GET /api/v1/skills/{name}/zip/{version}` — 下载指定版本 ZIP

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-009** | 正常下载 ZIP | Nacos Skill 存在 | `GET /api/v1/skills/{name}/zip/{version}` | 200，`Content-Type: application/zip`，`Content-Disposition` 含文件名 | P0 |
| **API-010** | Skill 不存在 | Nacos 无此 Skill | `GET /api/v1/skills/not_exist_skill/zip/1.0.0` | 404，`detail` 包含错误信息 | P0 |
| **API-011** | 版本不存在 | Skill 存在但版本不存在 | `GET /api/v1/skills/{name}/zip/9.9.9` | 502 或 404（取决于 Nacos 返回） | P0 |
| **API-012** | 空 Skill 名称 | 无 | `GET /api/v1/skills//zip/1.0.0` | 404 或 422 | P1 |
| **API-013** | 特殊字符 Skill 名称 | Skill 名称含特殊字符 | `GET /api/v1/skills/skill@#$%/zip/1.0.0` | 返回 404（URL 中特殊字符被转义） | P1 |
| **API-014** | ZIP 下载断点续传（Connection: keep-alive） | Nacos 支持 | `GET /api/v1/skills/{name}/zip/{version}` | `requests.Session` 保持连接复用 | P2 |

### 3.3 `GET /api/v1/skills/{name}/zip` — 下载最新版本 ZIP

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-015** | 正常下载最新版 ZIP | Nacos Skill 存在 | `GET /api/v1/skills/{name}/zip` | 200，ZIP 有效，filename 为 `{safe_name}.zip` | P0 |
| **API-016** | Skill 不存在 | 无 | `GET /api/v1/skills/not_exist/zip` | 404 | P0 |
| **API-017** | 最新版 ZIP 的 Content-Type | Nacos Skill 存在 | `GET /api/v1/skills/{name}/zip` | `Content-Type: application/zip` | P1 |
| **API-018** | 最新版 ZIP 文件大小 > 0 | Nacos Skill 存在 | `GET /api/v1/skills/{name}/zip` | 返回字节数 > 0 | P1 |

### 3.4 `GET /api/v1/skills/{name}` — 获取 Skill 详情

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-019** | 正常获取详情 | Nacos Skill 存在 | `GET /api/v1/skills/{name}` | 200，包含 `name`、`description`、`status` 等 | P0 |
| **API-020** | Skill 不存在 | 无 | `GET /api/v1/skills/not_exist` | 404，`detail` 包含错误信息 | P0 |
| **API-021** | 特殊字符 Skill 名称 | 无 | `GET /api/v1/skills/skill@#$%` | 404 | P2 |

### 3.5 `POST /api/v1/skills/login` — 登录获取 token

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-022** | 正常登录 | Nacos 服务正常 | `POST /api/v1/skills/login`（通过 `NacosSkillClient` 内部调用） | 获取 Bearer token，后续请求自动携带 | P0 |
| **API-023** | 认证失败 — 错误密码 | Nacos 服务正常 | `POST /api/v1/skills/login`（使用错误凭证） | 401，`NacosAuthError` 被正确抛出 | P0 |
| **API-024** | Token 过期自动重试 | Token 已过期 | 调用任意端点 | 内部触发重新登录，重试原请求，返回 200 | P0 |
| **API-025** | 登录地址与 API 地址不同 | 配置了 `login_addr` | 请求发送到 `login_addr` | 登录地址正确，不混淆 | P2 |

### 3.6 健康检查端点

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-026** | 健康检查正常 | 服务运行中 | `GET /health` | 200，`{"status": "ok", "version": "0.2.0"}` | P0 |
| **API-027** | Nacos 连接异常时健康检查 | Nacos 下线 | `GET /health` | 200 或 503（取决于实现），不影响服务可用性 | P1 |

### 3.7 全局异常处理

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **API-028** | 500 全局异常处理 | 代码异常 | 触发未捕获异常 | 500，`{"detail": "Internal server error"}` | P0 |

---

## 四、边界测试（Edge Case Tests）

### 4.1 数据边界

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **EC-001** | Nacos 返回 0 个 Skill | 空命名空间 | `GET /api/v1/skills` | 200，`total_count=0`，`items=[]` | P0 |
| **EC-002** | Nacos 返回大量 Skills（性能） | 1000+ Skills | `GET /api/v1/skills/all` | 请求在超时内完成，返回所有结果 | P1 |
| **EC-003** | Nacos 返回空 content 字段 | Nacos 返回异常数据 | `GET /api/v1/skills/{name}/md/{version}` | 返回 `content=""`，不崩溃 | P1 |
| **EC-004** | Nacos 返回空 resource 字段 | Nacos 返回异常数据 | `GET /api/v1/skills/{name}/md/{version}` | 返回空 `frontmatter`，不崩溃 | P1 |
| **EC-005** | 指令文件不存在 | Skill 无 SKILL.md | `GET /api/v1/skills/{name}/md/{version}` | 404 或 `detail` 包含 "无法获取" 信息 | P0 |
| **EC-006** | 缓存目录权限不足 | 文件系统无写权限 | `save_skill()` | 记录错误日志，不抛出异常 | P1 |
| **EC-007** | 缓存 manifest.json 格式错误 | 文件存在但内容非 JSON | `get_skill_manifest()` | 返回 `None`，记录警告 | P2 |
| **EC-008** | 缓存文件编码非 UTF-8 | 文件编码异常 | `get_skill_file()` | 返回 `(None, None)`，记录警告 | P2 |
| **EC-009** | Skill 名称为空字符串 | 无 | `GET /api/v1/skills/` | 404（匹配其他路由或返回错误） | P1 |

### 4.2 网络与超时边界

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **EC-010** | Nacos 连接超时 | Nacos 无响应 | 调用任意 API | 在 `timeout` 秒内抛出 `NacosSkillError` | P0 |
| **EC-011** | Nacos DNS 解析失败 | 无效 host | 调用任意 API | 抛出 `NacosSkillError`，错误信息含 DNS 失败 | P0 |
| **EC-012** | Nacos 返回非 JSON 响应 | Nacos 异常 | `GET /api/v1/skills` | 返回 500，错误信息含响应前 200 字符 | P1 |
| **EC-013** | Nacos 返回 401（Token 过期） | Token 过期 | `GET /api/v1/skills` | 自动重新登录并重试，返回 200 | P0 |
| **EC-014** | Nacos 返回 403（权限不足） | 无权限 | 调用 API | 401 或 500，错误信息清晰 | P1 |
| **EC-015** | Nacos 返回 503（服务不可用） | Nacos 维护中 | 调用 API | 500 或 502，错误信息清晰 | P1 |
| **EC-016** | ZIP 下载返回空数据 | Nacos 异常 | `GET /api/v1/skills/{name}/zip/{version}` | 返回 200 但内容为空（Nacos 行为），由调用方校验 | P2 |
| **EC-017** | 大文件 ZIP 下载（内存溢出） | Skill ZIP > 100MB | `GET /api/v1/skills/{name}/zip/{version}` | 请求在 timeout 内完成，不 OOM | P2 |
| **EC-018** | 并发下载同一个 Skill ZIP | 多个线程/请求 | 并发 10 次 `GET /api/v1/skills/{name}/zip/{version}` | 全部返回 200，无竞态条件 | P2 |

---

## 五、集成测试（Integration Tests）

### 5.1 端到端流程

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **IT-001** | 完整流程：登录 → 列表 → 详情 → ZIP 下载 | Nacos 服务正常 | 1. 初始化 `NacosSkillClient` 自动登录<br>2. `list_skills()`<br>3. `get_skill_detail(name)`<br>4. `download_skill_zip(name, version)` | 所有步骤成功，ZIP 可正常解压 | P0 |
| **IT-002** | 完整流程：登录 → 搜索 → ZIP 下载 | Nacos 服务正常 | 1. `search_skills(keyword="翻译")`<br>2. 从结果中选一个 Skill<br>3. `download_skill_zip()` | 搜索结果的 Skill 可成功下载 | P0 |
| **IT-003** | 完整流程：缓存命中优化 | 缓存目录有 Skill | 1. 首次调用 `get_skill_md()`（触发 Nacos + 缓存）<br>2. 再次调用 `get_skill_md()` | 第二次直接从缓存读取，不调用 Nacos | P0 |
| **IT-004** | 完整流程：缓存未命中 → 下载 → 缓存 → 再次读取 | 缓存目录无 Skill | 1. `get_skill_md()`（Nacos 下载 + 缓存）<br>2. `cache.get_skill_file()` | 第二次从缓存读取成功 | P0 |
| **IT-005** | Token 过期重连全流程 | Token 已过期 | 1. 使 token 过期（mock 401）<br>2. 调用 `get_skill_md()` | 自动重新登录，重试获取 | P0 |
| **IT-006** | 四级回退完整流程 — Level1 成功 | 指定版本存在 | `get_instruction_file(name, version)` | 从指定版本获取文件 | P1 |
| **IT-007** | 四级回退完整流程 — Level2 回退 | 指定版本不存在 | `get_instruction_file(name, version)` | 从 online 版本获取 | P1 |
| **IT-008** | 四级回退完整流程 — Level3 Console API | 指定版本不存在 + online 也不存在 | `get_instruction_file(name, version)` | 从 Console API 获取 offline Skill 元信息 | P2 |

### 5.2 配置集成

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **IT-009** | 环境变量覆盖 YAML 配置 | 有 YAML 配置文件 | 设置 `NACOS_SKILL_NACOS__SERVER_ADDR` 环境变量 | Config 使用环境变量值，优先级高于 YAML | P1 |
| **IT-010** | 默认配置加载 | 无 YAML、无环境变量 | `Config.load()` | 使用硬编码默认值（`http://192.168.1.118:8002`） | P1 |

### 5.3 模型集成

| 编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|------|---------|---------|---------|---------|--------|
| **IT-011** | SkillItem 字段映射验证 | Nacos API 返回标准 JSON | `SkillItem(**raw_data)` | 所有别名字段正确映射（`namespaceId` → `namespace_id`） | P1 |
| **IT-012** | SkillVersionDetail 兼容两种返回格式 | Console API + Client API 格式 | `SkillVersionDetail(**console_data)` | 两种格式均可正确解析 | P2 |

---

## 六、之前 Commit 改动的覆盖标注

> 以下用例直接覆盖最近的重大重构改动。

| 编号 | 覆盖的改动 | 相关 Commit |
|------|-----------|-------------|
| **FT-018** ~ **FT-024** | 新增 `download_skill_zip()` + ZIP 端点 | `2fd8a79` feat: 使用 Nacos 官方 API 下载 Skill ZIP |
| **API-009** ~ **API-018** | ZIP 下载端点的正常/异常路径 | `2fd8a79` + `5e377c4` refactor: 移除 LLM 调用 |
| **EC-013** | Token 过期自动重试逻辑（`_request` + `download_skill_zip` 两处） | `5e377c4` + `2fd8a79` |
| **EC-014** ~ **EC-017** | 网络异常处理（401/403/503/空响应） | `5e377c4` refactor |
| **IT-001** ~ **IT-008** | 完整端到端流程（重构后新架构） | `5e377c4` + `2fd8a79` |
| **IT-003** ~ **IT-004** | 缓存功能（重构前已有，需验证未回归） | `5e377c4` 移除 LLM 不应影响缓存 |
| **FT-009** ~ **FT-010** | 元数据发现端点（重构前已有，需验证未回归） | `5e377c4` |
| **API-022** ~ **API-024** | 登录/认证流程（重构前已有，需验证未回归） | `5e377c4` |
| **EC-001** ~ **EC-005** | 空结果/缺失数据边界（重构后新引入的路由减少） | `5e377c4` |

---

## 七、测试优先级说明

| 优先级 | 含义 | 覆盖率目标 |
|--------|------|-----------|
| **P0** | 核心路径，阻塞发布 | 100% 必须通过 |
| **P1** | 重要功能，影响用户体验 | ≥ 90% |
| **P2** | 辅助功能，边缘场景 | ≥ 80% |

---

## 八、测试策略建议

### 8.1 单元测试（Unit Tests）
- **模块**: `nacos_skill_client/` 下各模块
- **框架**: `pytest` + `unittest.mock`
- **重点**: `client.py` 的 `_request`、`_login`、`download_skill_zip`、`_parse_*` 解析函数

### 8.2 集成测试（Integration Tests）
- **模块**: 完整的 `NacosSkillClient` 流程
- **框架**: `pytest` + `TestClient`（FastAPI）
- **重点**: 真实 Nacos 服务连接（可配置 `NACOS_SKILL_NACOS__SERVER_ADDR` 指向测试环境）

### 8.3 接口测试（API Tests）
- **模块**: `api/` 下路由
- **框架**: `pytest` + `TestClient` + 依赖注入 mock
- **重点**: 每个端点的正常/异常路径，依赖注入链路的 mock

### 8.4 缓存测试（Cache Tests）
- **模块**: `nacos_skill_client/cache.py`
- **框架**: `pytest` + 临时目录 `tmp_path`
- **重点**: `save_skill`、`get_skill_file`、`has_skill`、`get_all_cached_skills`

### 8.5 测试数据
- 使用 `conftest.py` 中的 `mock_skill_items` fixture
- 新增 ZIP 下载测试用 mock ZIP 文件（`zipfile` 构造）
- 使用 `tmp_path` 管理测试用缓存目录

---

## 九、测试矩阵速查表

```
┌──────────────────────────┬───────┬───────────┬──────┬───────────┬──────────┐
│         模块             │ 正常  │ 边界/异常 │ 缓存 │  网络     │  集成    │
├──────────────────────────┼───────┼───────────┼──────┼───────────┼──────────┤
│ GET /skills              │  FT  │   EC-001  │      │  EC-010   │  IT-001  │
│ GET /skills/all          │  FT  │           │      │           │          │
│ GET /skills/search       │  FT  │   EC-002  │      │           │  IT-002  │
│ GET /skills/metadata     │  FT  │   EC-001  │      │           │          │
│ GET /skills/{name}       │  FT  │   EC-001  │      │           │          │
│ GET /skills/{name}/md    │  FT  │   EC-005  │  FT  │  EC-010   │  IT-003  │
│ GET /skills/{name}/zip   │  FT  │   EC-001  │      │  EC-010   │  IT-001  │
│ GET /skills/{name}/zip/{v}│ FT  │  EC-003   │      │  EC-010   │  IT-001  │
│ 登录/Token               │  FT  │   EC-013  │      │  EC-011   │  IT-005  │
│ 缓存                     │  FT  │   EC-006  │  FT  │           │  IT-004  │
│ 四级回退                 │  FT  │   EC-005  │      │           │  IT-006  │
└──────────────────────────┴───────┴───────────┴──────┴───────────┴──────────┘
```

---

## 十、补充说明

1. **Mock 策略**: 网络请求统一使用 `unittest.mock.patch` 或 `responses` 库 mock Nacos API，避免测试依赖外部服务。

2. **ZIP 测试**: 使用 `io.BytesIO` + `zipfile` 构造测试 ZIP 文件，模拟 Nacos 返回的 ZIP 二进制流。

3. **Token 过期测试**: 通过 mock `requests.Session.get` 首次返回 401，第二次返回 200，验证自动重试逻辑。

4. **性能测试**: FT-002、EC-002 涉及大数据量场景，建议在 CI 中使用 mock 大量数据验证分页逻辑。

5. **回归测试**: `5e377c4` commit 移除了 `compat_routes.py`、`router.py`、`test_router.py` 等文件，确保这些文件不再存在于代码中（作为回归检查）。
