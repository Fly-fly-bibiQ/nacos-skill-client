# nacos-skill-client 测试用例审核报告

**审核日期**: 2026-04-20
**审核人**: 后端架构师 (backend-architect)
**审核文件**: `tests/TEST_CASES.md` (19 条测试用例)
**参考源码**: events.ts, chatReducer.ts, App.tsx, sse.ts, compat_routes.py, stream.py, ChatTimeline.tsx, Composer.tsx, SkillPanel.tsx, ToolCallItem.tsx, App.css

---

## 审核结论：需要修改

**理由**：测试用例整体结构合理，但存在多处预期结果与实际实现不一致、关键场景遗漏、以及可用性不足的问题。以下逐项列出。

---

## 一、准确性问题（预期结果与实际实现不符）

### 1. TC-004 / TC-005: 后端 SSE 事件类型错误 ⚠️ 严重

**问题**：测试用例描述的事件类型（`discovered`, `no_skill`, `skill_selected`, `instruction_loaded`, `agent_error`）是**后端 LangGraph Agent 内部事件**，但 `compat_routes.py` 已经做了映射转换：

```python
# compat_routes.py 事件映射
if event["event"] == "discovered":
    continue                    # 丢弃 discovered
elif event["event"] == "skill_selected":
    yield {"event": "tool_call", "data": {"name": "load_skill", ...}}  # 映射为 tool_call
elif event["event"] == "no_skill":
    pass                        # 直接跳过，不发送事件
elif event["event"] == "instruction_loaded":
    pass                        # 丢弃
elif event["event"] == "content":
    yield {"event": "text", "data": {"content": ...}}  # 映射为 text
elif event["event"] == "error":
    yield {"event": "agent_error", ...}
elif event["event"] == "done":
    yield {"event": "done", ...}
```

**实际从 SSE 客户端收到的事件类型**（见 `sse.ts` 的 `STREAM_EVENT_TYPES`）：
- `thinking` — 来自 LLM 的 thinking tokens（如果启用）
- `text` — 普通文本内容
- `tool_call` — Skill 选择（对应后端的 `skill_selected`）
- `tool_result` — 工具结果
- `done` — 完成
- `error` — 错误（前端类型名为 `error`，后端发送为 `agent_error`）

**TC-004 实际预期应为**：
- 丢弃 `discovered` → 前端看不到
- 无 Skill 匹配时：跳过 `no_skill` 事件 → 直接 `text*` → `done`
- 不出现 `tool_call(load_skill)` 事件
- 错误事件前端收到的类型为 `error`（不是 `agent_error`）

**TC-005 实际预期应为**：
- 匹配到 Skill 时：出现 `tool_call(load_skill)` 事件 + `text("使用 Skill: xxx")` 事件（这是 compat_routes.py 硬编码的行为）
- 不出现 `skill_selected`、`instruction_loaded` 事件

**建议修改**：TC-004 和 TC-005 的预期结果应改为 SSE 客户端收到的事件类型，而非后端内部事件类型。

### 2. TC-011 / TC-012: 前端事件类型描述错误 ⚠️ 严重

**TC-011** 提到 `thinking` 事件和 `text` 事件逐字显示：
- `sse.ts` 确实监听 `thinking` 和 `text` 事件
- 但 `chatReducer.ts` 中的 `stream_event` 处理确实区分了 `thinking`（更新 `thinking` 字段）和 `text`（更新 `response` 字段）
- **问题**：测试预期说"逐字显示"——实际是流式拼接 `response` 字符串，并非每收到一个 `text` 事件就追加一个字符。`stream.py` 中 `_stream_llm_content` 的每个 chunk 可能包含多个字符
- **结论**：描述可接受，但"逐字"表述不够精确

**TC-012** 提到 `tool_call` 事件时 tool_name=load_skill：
- 正确。`sse.ts` 监听 `tool_call`，`chatReducer.ts` 中 `upsertToolCall` 处理 `tool_call` 类型，`compat_routes.py` 将 `skill_selected` 映射为 `tool_call(load_skill)`
- **但**：`compat_routes.py` 在发送 `tool_call` 后还发送了一条 `text("使用 Skill: xxx")`，所以 TC-012 预期中应额外提到会有一行 "使用 Skill: xxx" 的文本
- **还有**：`tool_result` 事件在 Skill 场景中**不会出现**。`compat_routes.py` 没有映射 `tool_result` 事件，`stream.py` 也不产生 `tool_result`。测试用例提到"可能出现 tool_result 事件"是不准确的。

### 3. TC-014: /skills 命令回复格式问题 ⚠️ 中等

**问题**：测试用例预期"Markdown 渲染（`**名称**: 描述\n  - path: \`路径\``）"

实际 `App.tsx` 中的 `skillsAsMarkdown` 函数生成格式为：
```markdown
## Available Skills
- **{name}**: {description}
  - path: `{path}`
```

注意：
1. 有 "## Available Skills" 标题
2. `path` 前有空格（2 空格缩进）
3. 如果 `skill.description` 为空字符串，输出 "No description"（见 `App.tsx`）

**建议**：测试预期应明确标题行和内容格式。

### 4. TC-014 / TC-015: 系统消息的视觉表现描述不够精确

`ChatTimeline.tsx` 中：
- 系统消息的 header 显示 **"Command"**（不是通用的"系统消息"）
- CSS 类名是 `message--system`，背景是 `linear-gradient(160deg, #fffef8, #fff7e8)`（淡黄色）
- 用户消息的 header 显示 **"User"**，CSS 类名是 `message--user`

测试用例 TC-014/015 说"灰色背景或特殊样式"——实际上系统消息是**淡黄色背景**，不是灰色。

### 5. TC-008: 初始消息文本错误

**问题**：测试用例预期显示 "Hello! Please choose a skill, or type /skills to list them."

**实际 `ChatTimeline.tsx`** 中：
```tsx
{entries.length === 0 && (
  <div className="empty-state">
    <h3>Start a conversation</h3>
    <p>Paste a task, URL, or command objective. The full execution chain will stream here.</p>
  </div>
)}
```

初始状态显示的是 **"Start a conversation"** 和 **"Paste a task, URL, or command objective..."**，不是 "Hello!"。

---

## 二、覆盖率不足 / 遗漏的测试点

### 6. 缺少：Skills 加载失败场景 ❌

- **`App.tsx`** 有 `skills_failed` 的 catch 分支，`SkillPanel` 有 `error` prop 和 `skills-panel__error` CSS
- **TC-018** 测试的是后端停止后的错误，但没有单独测试 skills 加载失败的 UI 表现
- **建议新增 TC**：网络错误导致 skills 加载失败时，SkillPanel 是否显示错误信息

### 7. 缺少：输入框的 disabled/submit button 状态 ❌

- `Composer.tsx` 中 submit 按钮的 disabled 条件是 `disabled || !value.trim()`
- 即：流式传输期间**或输入为空**时按钮禁用
- 测试用例 TC-010 说"按 Enter 后发送按钮可用"——这是正确的，但应明确**发送过程中按钮应禁用**
- **建议修改 TC-010**，增加发送过程中按钮不可点击的验证

### 8. 缺少：空消息发送被阻止 ❌

- `Composer.tsx` 的 `submit()` 函数开头有 `if (!nextValue) return`
- 用户发送空消息（只输入空格）时应被静默阻止
- **建议新增 TC**：输入空白字符后发送

### 9. 缺少：多行输入 / Shift+Enter 行为 ❌

- `Composer.tsx` 的 `onKeyDown` 条件是 `event.key === "Enter" && !event.shiftKey`
- 意味着 `Shift+Enter` 应该是换行而不是发送
- 测试用例 TC-010 只测试了 Enter 发送，未测试 `Shift+Enter` 换行
- **建议新增 TC**：Shift+Enter 是否换行

### 10. 缺少：Stream 中断后重新发送 ❌

- `App.tsx` 中 `handleSend` 开头有 `if (state.isStreaming) return`
- 流式传输期间发送第二条消息应被忽略
- **建议修改 TC-011**：在流式回复过程中尝试发送第二条消息，应被忽略

### 11. 缺少：Thread 编号连续性 ❌

- `App.tsx` 中 `createThread` 使用 `state.threadOrder.length + 1` 生成编号
- 测试用例 TC-016 测试了创建 Thread 2 和切换，但没有测试连续创建多个 Thread
- **建议新增 TC**：连续创建 Thread 3、Thread 4，验证编号正确递增

### 12. 缺少：流式传输中 New Thread 按钮禁用验证 ❌

- `App.tsx` 中 New Thread 按钮的 disabled 条件是 `state.isStreaming`
- **建议修改 TC-016**：在流式传输期间点击 New Thread 应无反应

### 13. 缺少：Thread 切换时输入框禁用验证 ❌

- `App.tsx` 中 Thread 下拉框的 disabled 条件是 `state.isStreaming`
- **建议新增 TC**：流式传输时 Thread 下拉框应禁用

### 14. 缺少：/prompt 命令的 /prompt 请求失败处理 ❌

- `App.tsx` 中 `/prompt` 处理有 catch 分支，会显示 "Error: ..." 的系统消息
- **建议新增 TC**：后端无 /prompt 端点时，前端应显示错误消息

### 15. 缺少：ToolCallItem 展开/折叠行为 ❌

- `ToolCallItem.tsx` 实现了结果展开/折叠（最多显示 12 行）
- `chatReducer.ts` 有 `toggle_tool_expand` action
- 测试用例完全没有覆盖这个交互
- **建议新增 TC**：工具调用结果过长时，是否显示"Show X more lines"按钮；点击是否展开/折叠

### 16. 缺少：ToolCallItem 状态可视化（running/success/failed）❌

- `ToolCallItem.tsx` 根据 `tool.status` 显示不同颜色的圆点
- `chatReducer.ts` 中 `applyToolResult` 根据内容是否以 "[FAILED]" 开头判断成功/失败
- 测试用例 TC-012 提到 tool_call 但未描述视觉表现
- **建议修改 TC-012**：增加工具调用卡片的视觉状态验证

### 17. 缺少：SkillPanel 中 "In Use" 标记 ❌

- `SkillPanel.tsx` 中当 `skill.name === activeSkillName` 时显示 "In Use" 徽章
- `chatReducer.ts` 中当 `stream_event` 为 `tool_call` 且 name 为 `load_skill` 时设置 `activeSkillName`
- 测试用例 TC-012 提到"左侧面板高亮显示当前使用的 Skill"但没有描述 "In Use" 徽章
- **建议修改 TC-012**：明确 Skill 面板应显示 "In Use" 徽章

### 18. 缺少：流式传输中 Thinking 阶段 UI ❌

- `ChatTimeline.tsx` 当 `entry.thinking` 非空时显示 Thinking 面板
- `sse.ts` 监听 `thinking` 事件
- 测试用例 TC-011 提到 `thinking` 事件但没有描述 Thinking 面板的视觉表现
- **建议修改 TC-011**：明确 Thinking 面板的显示（标题 "Thinking"，内容在 pre 标签中）

---

## 三、可用性/描述问题

### 19. TC-002: 技能数量硬编码问题 ⚠️

预期要求 "skills 数量 >= 100（186 个 agent）"。这个数量是**运行时动态的**，依赖于 Nacos 中实际注册的 skill 数量。不同环境可能完全不同。

**建议**：改为 "返回的 skills 数量应与实际注册数量一致，非空"

### 20. TC-004: curl 超时时间不一致 ⚠️

- TC-004 设置 `-m 30`（30秒）
- TC-005 设置 `-m 60`（60秒）
- 但对于无 Skill 匹配的场景，30秒应该足够。有 Skill 的场景因为涉及指令文件加载，60秒合理。
- **建议**：统一说明原因

### 21. TC-019: 未说明验证连接恢复的完整性 ❌

TC-019 只测试了新消息能发送，但没有验证：
- 之前的 Thread 历史是否正常
- Skills 面板是否正常
- **建议**：增加恢复后的页面状态检查

---

## 四、正面评价

1. ✅ 测试用例组织结构清晰（后端 API → 前端页面 → SSE 集成 → 特殊功能 → 网络/错误处理）
2. ✅ 每个用例都有明确的编号、前置条件、操作步骤、预期结果
3. ✅ TC-018/TC-019 覆盖了服务启停的韧性场景，很好
4. ✅ TC-016 覆盖了 Thread 切换场景，这是核心功能
5. ✅ TC-017 验证了 Vite proxy 转发，这是部署层面的关键测试

---

## 五、审核总结

| 维度 | 评分 | 说明 |
|------|------|------|
| 覆盖率 | ⚠️ 不足 | 缺少 7 个重要测试点（Skills 加载失败、空消息、Shift+Enter、多 Thread、工具展开、thinking UI、In Use 徽章） |
| 准确性 | ❌ 有偏差 | TC-004/005/008/011/012 的事件类型和预期结果与实际实现不符 |
| 可用性 | ⚠️ 一般 | 部分视觉描述不准确（灰色背景 vs 淡黄色、初始消息文本） |
| 完整性 | ⚠️ 不足 | 缺少输入验证、空值处理、边界行为测试 |

**最终结论**：**需要修改**。主要需修正 TC-004/005/008/011/012 的准确性问题，并新增约 7 条测试用例覆盖遗漏场景。
