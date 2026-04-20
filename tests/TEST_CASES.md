# nacos-skill-client 集成测试用例

> 人工测试用例清单，按用例编号执行，测试后填写实际结果、截图和状态。
> 前置要求：后端在 8899 端口运行，前端在 5173 端口运行。

---

## 一、后端 API 测试

### TC-001: 健康检查
- **前置条件**: 后端服务已启动（8899 端口）
- **操作步骤**:
  1. 浏览器访问 `http://localhost:8899/health`
  2. 或使用 curl: `curl http://localhost:8899/health`
- **预期结果**: 返回 `{"status": "ok"}` 或类似健康状态 JSON
- **截图**:
- **状态**: PASS / FAIL / N/A

### TC-002: 获取 Skills 列表
- **前置条件**: 后端已连接 Nacos 服务
- **操作步骤**:
  1. 浏览器访问 `http://localhost:8899/api/skills`
  2. 或使用 curl: `curl http://localhost:8899/api/skills`
- **预期结果**:
  - 返回 HTTP 200
  - JSON 格式: `{ "skills": [{ "name": "...", "description": "...", "path": "..." }] }`
  - skills 数量 >= 100（186 个 agent）
- **截图**:
- **状态**: PASS / FAIL / N/A

### TC-003: 获取 System Prompt
- **前置条件**: 后端已启动
- **操作步骤**:
  1. 浏览器访问 `http://localhost:8899/api/prompt`
  2. 或使用 curl: `curl http://localhost:8899/api/prompt`
- **预期结果**:
  - 返回 HTTP 200
  - JSON 格式: `{ "prompt": "..." }`
  - prompt 内容包含 System Prompt 文本（非空，长度 > 1000）
- **截图**:
- **状态**: PASS / FAIL / N/A

### TC-004: SSE 流式聊天 — 通用问题（无 Skill 匹配）
- **前置条件**: 后端、LLM 均正常运行
- **操作步骤**:
  1. 使用 curl: `curl -s -N -m 30 "http://localhost:8899/api/chat/stream?message=你好+请介绍你自己"`
  2. 观察输出事件序列
- **预期结果**:
  - 返回 HTTP 200，Content-Type: `text/event-stream`
  - `compat_routes.py` 会丢弃 `discovered` 事件、跳过 `no_skill` 事件
  - 前端实际收到的事件序列: `text*`（流式内容）→ `done`
  - `text` 事件中的数据应包含 LLM 回复内容（非空，有实际文本）
  - 不出现 `tool_call` 事件（无 Skill 匹配时不应发送 tool_call）
  - 错误事件前端收到的类型为 `agent_error`（后端使用此事件名）
- **截图**: curl 完整输出
- **状态**: PASS / FAIL / N/A

### TC-005: SSE 流式聊天 — 含 Skill 关键词（可能匹配）
- **前置条件**: 后端、LLM 均正常运行
- **操作步骤**:
  1. 使用 curl: `curl -s -N -m 60 "http://localhost:8899/api/chat/stream?message=帮我搜索飞书文档"`
  2. 观察输出事件序列
- **预期结果**:
  - `compat_routes.py` 映射后的前端事件序列:
    - 匹配到 Skill: `tool_call(load_skill)` → `text("使用 Skill: xxx")` → `text*`（LLM 回复）→ `done`
    - 未匹配: 直接 `text*` → `done`
  - `text` 事件中有 LLM 回复内容
  - 如果匹配到 Skill: `tool_call` 的 name 为 `load_skill`，args 包含 `skill_name`
  - 不出现 `agent_error`
- **截图**: curl 完整输出
- **状态**: PASS / FAIL / N/A

### TC-006: SSE 长消息测试
- **前置条件**: 后端、LLM 均正常运行
- **操作步骤**:
  1. 使用 curl: `curl -s -N -m 60 "http://localhost:8899/api/chat/stream?message=请详细解释一下什么是微服务架构，包括其优点、缺点、适用场景和实现方案"`
  2. 观察完整输出
- **预期结果**:
  - 完整流式输出不中断
  - `content` 事件中的内容量 > 100 字符
  - 最终以 `done` 事件结束
- **截图**: curl 完整输出（或内容片段）
- **状态**: PASS / FAIL / N/A

### TC-007: 元数据发现接口
- **前置条件**: 后端已启动
- **操作步骤**:
  1. `curl http://localhost:8899/api/v1/skills/metadata`
- **预期结果**:
  - 返回 HTTP 200
  - JSON: `{ "total_count": 186, "skills": [{ "name": "...", "description": "..." }] }`
  - total_count = 186
- **截图**:
- **状态**: PASS / FAIL / N/A

---

## 二、前端页面测试

### TC-008: 页面加载与布局
- **前置条件**: 前端已启动（5173 端口），后端也在运行
- **操作步骤**:
  1. 浏览器打开 `http://localhost:5173`
  2. 观察页面整体布局
- **预期结果**:
  - 页面标题显示 "Nacos Skill Agent"
  - 布局包含三区域：顶部标题栏 + 左侧 Skills 面板 + 右侧聊天面板
  - 左侧面板显示 "Available Skills" 标题
  - 右侧聊天区域初始状态显示空状态:
    - 标题: "Start a conversation"
    - 描述: "Paste a task, URL, or command objective..."
  - 底部显示输入框和发送按钮
- **截图**: 完整页面截图
- **状态**: PASS / FAIL / N/A

### TC-009: Skills 面板显示
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 观察左侧 Skills 面板
  2. 检查面板底部显示的技能数量
- **预期结果**:
  - Skills 面板正确加载完成（无错误提示）
  - 显示 "186 skills" 或类似数量
  - 面板无加载超时
- **截图**: Skills 面板截图
- **状态**: PASS / FAIL / N/A

### TC-010: 聊天输入框和发送按钮
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 点击底部输入框
  2. 输入文字（如 "测试消息"），观察发送按钮状态
  3. 清空输入框（或只输入空格），观察发送按钮状态
  4. 输入文字，按 Enter 发送
  5. 在流式回复过程中，尝试再次点击发送按钮
  6. 测试 Shift+Enter 组合键
- **预期结果**:
  - 有输入内容时发送按钮可用
  - **空输入时发送按钮禁用**（`Composer` 中 `submit()` 有 `if (!nextValue) return`）
  - 按 Enter 后发送，发送后输入框清空
  - **流式期间发送按钮禁用**（`disabled={state.isStreaming}`）
  - Shift+Enter 应换行而不是发送
- **截图**: 发送后的聊天面板
- **状态**: PASS / FAIL / N/A

---

## 三、SSE 流式聊天 — 前端集成测试

### TC-011: 发送消息并接收回复（无 Skill 匹配）
- **前置条件**: 页面已加载，后端和 LLM 正常
- **操作步骤**:
  1. 在输入框输入: `你好`
  2. 按 Enter 发送
  3. 观察聊天时间线的变化
- **预期结果**:
  - 用户消息 "你好" 显示为蓝色气泡，header 显示 "User"
  - 助手消息区域依次显示:
    1. 空状态 → 出现助手回复卡片
    2. 如果收到 `thinking` 事件：显示 Thinking 面板（标题 "Thinking"，内容在 pre 标签中）
    3. 流式文本内容（`text` 事件 — response 字段拼接）
    4. 完成状态（`done` 后不再变化，phase=done）
  - 发送期间输入框禁用，发送按钮禁用，New Thread 按钮禁用
  - 回复完成后输入框恢复可用
  - 无 `streamError` 显示
  - **边界测试**：回复过程中尝试再次发送消息，应被忽略（handleSend 有 `if (state.isStreaming) return`）
- **截图**: 完整的流式回复过程（至少 2 张：正在回复时 + 回复完成时）
- **状态**: PASS / FAIL / N/A

### TC-012: 发送消息并接收回复（含 Skill 匹配）
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 在输入框输入: `帮我翻译这段文本：Hello World`
  2. 按 Enter 发送
  3. 观察聊天时间线
- **预期结果**:
  - 可能出现 `tool_call(load_skill)` 事件 — 显示工具调用卡片
    - 卡片显示 tool name: `load_skill`, args 含 `skill_name`
    - 运行中显示圆点（不同颜色区分 running/success/failed）
    - 点击卡片可展开/折叠结果（最多 12 行后显示 "Show X more lines"）
  - `compat_routes.py` 在 tool_call 后还会发送 `text("使用 Skill: xxx")`
  - 最终 `text` 事件显示翻译结果
  - 左侧面板该 Skill 上显示 "In Use" 徽章（当 `activeSkillName` 匹配时）
  - 无 `tool_result` 事件（compat_routes.py 不映射 tool_result）
- **截图**: 包含工具调用卡片的完整过程
- **状态**: PASS / FAIL / N/A

### TC-013: 发送长消息测试
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 在输入框输入: `请详细解释一下 Python 的装饰器，包括其原理、用法和常见场景`
  2. 按 Enter 发送
  3. 观察完整回复过程
- **预期结果**:
  - 完整流式回复不中断
  - 最终回复内容量 > 100 字符
  - 无 `agent_error` 显示
- **截图**: 完整回复内容
- **状态**: PASS / FAIL / N/A

---

## 四、特殊功能测试

### TC-014: /skills 命令
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 在输入框输入: `/skills`
  2. 按 Enter 发送
- **预期结果**:
  - 显示一个系统消息条目（**淡黄色背景** `linear-gradient(160deg, #fffef8, #fff7e8)`）
  - header 显示 "Command"
  - 内容格式: `## Available Skills\n- **{name}**: {description} (或 "No description")\n  - path: \`{path}\``
  - 所有 Skills 列表以 Markdown 代码块形式展示
- **截图**: /skills 命令的回复
- **状态**: PASS / FAIL / N/A

### TC-015: /prompt 命令
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 在输入框输入: `/prompt`
  2. 按 Enter 发送
- **预期结果**:
  - 显示一个系统消息条目（**淡黄色背景**）
  - header 显示 "Command"
  - 内容包含 System Prompt 的 Markdown 代码块
  - **错误处理**：如果 `/api/prompt` 失败，应显示 "Error: ..." 的系统消息（catch 分支）
- **截图**: /prompt 命令的回复
- **状态**: PASS / FAIL / N/A

### TC-016: 创建新 Thread
- **前置条件**: 页面已加载（默认 Thread 1）
- **操作步骤**:
  1. 点击顶部 "New Thread" 按钮
  2. 观察 Thread 下拉列表
  3. 连续点击两次 "New Thread"，创建 Thread 2 和 Thread 3
  4. 在 Thread 3 中输入消息并发送
  5. 切换回 Thread 1
  6. 在流式传输期间尝试点击 "New Thread" 和切换 Thread 下拉框
- **预期结果**:
  - Thread 下拉列表显示 "Thread 1"、"Thread 2"、"Thread 3"
  - 编号连续递增
  - 每个 Thread 的聊天历史相互独立
  - 在 Thread 3 发送消息后，Thread 1 和 Thread 2 的聊天历史不受影响
  - 切换回 Thread 1，消息历史恢复
  - **流式期间**：New Thread 按钮应禁用（disabled），Thread 下拉框应禁用
- **截图**: Thread 切换截图
- **状态**: PASS / FAIL / N/A

---

## 四（续）：边界行为和交互测试

### TC-015b: Skills 加载失败 UI 表现
- **前置条件**: 后端运行但 /api/skills 返回 500 错误，或前端无法访问后端
- **操作步骤**:
  1. 停止后端服务
  2. 刷新前端页面
- **预期结果**:
  - 页面不崩溃
  - Skills 面板可能显示错误提示或保持空状态
  - 聊天区域仍然可用
- **截图**: 页面状态
- **状态**: PASS / FAIL / N/A

### TC-015c: 空消息发送被阻止
- **前置条件**: 页面已加载
- **操作步骤**:
  1. 在输入框中只输入空格或留空
  2. 按 Enter 发送
- **预期结果**:
  - 不出现用户消息
  - 发送按钮应为禁用状态
  - 页面无错误
- **截图**:
- **状态**: PASS / FAIL / N/A

## 五、网络层和错误处理测试

### TC-017: Vite Proxy 转发验证
- **前置条件**: 前端和后端均运行
- **操作步骤**:
  1. 浏览器打开 `http://localhost:5173`
  2. 打开浏览器开发者工具 → Network 面板
  3. 刷新页面，观察请求
  4. 查看 `/api/skills` 请求的 URL 和响应
- **预期结果**:
  - `/api/skills` 请求 URL 为 `http://localhost:5173/api/skills`（前端域）
  - 但响应数据来自后端（非 502）
  - 说明 Vite proxy 正确转发到 `http://127.0.0.1:8899`
- **截图**: Network 面板截图（显示请求 URL 和 200 响应）
- **状态**: PASS / FAIL / N/A

### TC-018: SSE 连接错误处理
- **前置条件**: 前端运行，停止后端服务
- **操作步骤**:
  1. 前端页面打开
  2. 停止后端服务（Ctrl+C 或在另一终端 kill）
  3. 在前端发送一条消息
- **预期结果**:
  - 不出现页面崩溃或白屏
  - 可能显示错误提示（stream_error）
  - 输入框恢复可用
- **截图**: 错误提示或页面状态
- **状态**: PASS / FAIL / N/A

### TC-019: 后端恢复后自动恢复连接
- **前置条件**: 后端已停止，前端在 TC-018 的状态
- **操作步骤**:
  1. 重新启动后端服务
  2. 在前端发送一条新消息
- **预期结果**:
  - 新消息可以正常发送并收到回复
  - 无连接残留错误
- **截图**: 恢复后的正常回复
- **状态**: PASS / FAIL / N/A

---

## 测试执行记录

| 用例编号 | 状态 | 备注 | 执行时间 |
|---------|------|------|---------|
| TC-001 | | | |
| TC-002 | | | |
| TC-003 | | | |
| TC-004 | | | |
| TC-005 | | | |
| TC-006 | | | |
| TC-007 | | | |
| TC-008 | | | |
| TC-009 | | | |
| TC-010 | | | |
| TC-011 | | | |
| TC-012 | | | |
| TC-013 | | | |
| TC-014 | | | |
| TC-015 | | | |
| TC-016 | | | |
| TC-017 | | | |
| TC-018 | | | |
| TC-019 | | | |
