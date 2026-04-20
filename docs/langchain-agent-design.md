# LangChain Agent 集成架构设计

## 1. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                        User Query                         │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│              POST /api/v1/chat (API Layer)                │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│               Agent Manager (agent/manager.py)            │
│  ┌───────────────────────────────────────────────────┐   │
│  │  LangChain Agent (ReAct / Tool Calling)           │   │
│  │   System Prompt: "Available tools: {skill_list}"   │   │
│  └───────────────┬───────────────────────────────────┘   │
│                  │                                        │
│  ┌───────────────▼───────────────┐                       │
│  │    NacosToolLoader            │                       │
│  │  • scan_skills_metadata()     │                       │
│  │  • load_skill() → instructions│                       │
│  │  • register Tool(name, desc)  │                       │
│  └───────────────────────────────┘                       │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│              NacosSkillClient (nacos_skill_client/)       │
│  • list_skills() → 获取所有 Skill 元数据                   │
│  • get_skill_md() → 下载 SKILL.md                        │
│  • download_skill_zip() → 下载完整 ZIP                   │
│  • cache → 本地缓存                                        │
└──────────────────────────────────────────────────────────┘
```

## 2. 核心模块设计

### 2.1 NacosToolLoader (`nacos_skill_client/tools/loader.py`)

从 Nacos 动态加载 Skill 为 LangChain Tool 对象。

```python
class NacosToolLoader:
    """将 Nacos Skill 转换为 LangChain Tool。"""

    def __init__(self, client: NacosSkillClient, config: Config):
        self.client = client
        self.config = config
        self.tools: dict[str, BaseTool] = {}

    def load_all_tools(self, namespace_id: str | None = None) -> list[BaseTool]:
        """扫描所有 Skill 并注册为 LangChain Tools。"""
        # 1. 扫描元数据
        metadata = self.client.scan_skills_metadata(namespace_id)
        # 2. 为每个 Skill 加载指令内容
        tools = []
        for meta in metadata:
            skill = self.load_skill_tool(meta)
            tools.append(skill)
            self.tools[meta.name] = skill
        return tools

    def load_skill_tool(self, metadata: SkillMetadata) -> BaseTool:
        """将单个 Skill 转换为 LangChain Tool。"""
        # 1. 从缓存或 Nacos 加载 SKILL.md
        content = self.client.get_skill_md(metadata.name, metadata.version)
        instructions = _extract_body(content.get("content", ""))

        # 2. 构造 Tool description（从 frontmatter）
        description = metadata.description or instructions[:200]

        # 3. 构造动态工具函数
        def tool_func(query: str, skill_name: str = metadata.name) -> str:
            return f"Executing {skill_name} with: {query}"

        # 4. 返回 StructuredTool
        return StructuredTool.from_function(
            name=metadata.name,
            description=description,
            func=tool_func,
        )
```

### 2.2 Tool 注册策略（关键决策）

**不是「一个 Tool 对应一个文件路径」，而是「一个 Tool 对应一个 Skill 函数」**

LangChain 的 `@tool` 装饰器将 Python 函数注册为 Tool：
```python
@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the customer database for records matching the query."""
    return f"Found {limit} results for '{query}'"
```

**我们的映射关系**：
```
Nacos Skill (name + description + instructions) → Python 函数 → @tool 装饰 → LangChain Tool
```

每个 Skill 对应一个 `@tool` 装饰的函数，函数体内读取 SKILL.md 指令内容执行。Tool 的 `description` 从 frontmatter description 提取，帮助 Agent 自动路由。

**为什么不是文件路径加载**：
- LangChain 的 `@tool` 装饰器绑定的是**函数**而非文件路径
- 每个 Skill 需要有自己的执行逻辑（函数体），不只是读取文件
- Skill 的指令内容（SKILL.md body）作为函数执行的上下文/约束条件
- 这样 Agent 看到的 `description` 是具体的功能描述，LLM 才能做出正确的路由判断

### 2.3 Agent 配置

**Agent 创建方式**（基于 LangChain 最新 `create_agent` API）：

```python
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

# 初始化 LLM 模型
model = init_chat_model("claude-sonnet-4-6", temperature=0.0)

# 创建 Agent
agent = create_agent(
    model=model,
    tools=[weather_tool, file_tool, code_tool],  # 所有 Nacos Skills 作为 Tools
    system_prompt=SYSTEM_PROMPT,  # 包含可用工具列表
    checkpointer=checkpointer,    # 对话记忆
)

# 执行 Agent
response = agent.invoke(
    {"messages": [{"role": "user", "content": query}]},
    config={"configurable": {"thread_id": "1"}},
)
```

**Agent 类型选择**：

| 类型 | 适用场景 | 推荐度 |
|------|---------|--------|
| **`create_agent` (Tool Calling)** | GPT-4o-mini / Claude 等原生支持 tool_call 的模型 | ⭐⭐⭐⭐⭐ |
| **ReAct** | 不支持 tool_call 的模型 | ⭐⭐⭐ |

```python
class AgentConfig(BaseModel):
    """Agent 配置。"""
    enabled: bool = Field(default=False, description="是否启用 Agent 模式")
    llm_provider: str = Field(default="openai", description="LLM provider (openai/anthropic/local)")
    model_name: str = Field(default="gpt-4o-mini", description="模型名称")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_iterations: int = Field(default=10, ge=1, description="最大思考轮次")
    max_time: int = Field(default=120, ge=1, description="最大执行时间(秒)")
    max_skills_to_load: int = Field(default=50, ge=1, description="最大加载 Skill 数量")
    agent_type: str = Field(default="tool-calling", description="Agent 类型 (tool-calling/react)")
```

**Agent 类型选择**：

| 类型 | 适用场景 | 推荐度 |
|------|---------|--------|
| **Tool Calling** | GPT-4o-mini / Claude 等原生支持 tool_call 的模型 | ⭐⭐⭐⭐⭐ |
| **ReAct** | 不支持 tool_call 的模型 | ⭐⭐⭐ |
| **Structured Chat** | 需要多轮对话的复杂场景 | ⭐⭐⭐⭐ |

**推荐**：默认 Tool Calling（GPT-4o-mini），通过配置切换到其他 provider。

### 2.4 缓存策略

复用现有 `SkillCache`：
- `get_skill_md()` 已有本地缓存机制（`.skill_cache/`）
- Tool 描述缓存：将 metadata（name + description）缓存到本地，避免频繁调用 Nacos API
- 缓存 TTL 通过 `SkillLoaderConfig.metadata_cache_ttl_minutes` 控制

## 3. API 层新增端点

### 3.1 `POST /api/v1/chat` — 与 Agent 对话

```
POST /api/v1/chat
{
  "message": "北京的天气怎么样？",
  "stream": false
}

Response:
{
  "answer": "北京今天晴，气温 22-28°C...",
  "tool_used": "weather_check",
  "thinking_steps": ["分析意图 → 选择工具: weather_check → 执行"],
  "took_ms": 3200
}
```

### 3.2 `GET /api/v1/skills/tools` — 获取 Tools 列表

```
Response:
{
  "tools": [
    {"name": "weather_check", "description": "查询天气...", "metadata": {...}},
    {"name": "file_search", "description": "搜索文件...", "metadata": {...}}
  ],
  "total": 5
}
```

### 3.3 `POST /api/v1/skills/tools/reload` — 重新加载 Tools

```
Response:
{
  "loaded": 5,
  "total": 5,
  "reload_time_ms": 1500
}
```

### 3.4 `GET /api/v1/skills/scan` — 扫描可用 Skills

```
Response:
{
  "skills": [
    {"name": "weather_check", "description": "查询天气...", "version": "1.0.0"}
  ],
  "total": 5
}
```

## 4. 依赖变更

```toml
[project.optional-dependencies]
agent = [
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
    "langchain-anthropic>=0.3.0",
    "langchain-community>=0.3.0",
]

[project.scripts]
nacos-skill = "nacos_skill_client.cli:main"
nacos-agent = "nacos_skill_client.agent.cli:main"  # 新增 CLI
```

**设计原则**：LangChain 通过 optional extras 提供，`pip install nacos-skill-client` 基础安装不包含 LangChain，`pip install nacos-skill-client[agent]` 才安装 Agent 支持。

## 5. 目录结构

```
nacos_skill_client/
├── __init__.py          # 导出 NacosSkillClient
├── tools/               # 新增：LangChain Tools
│   ├── __init__.py      # 导出 NacosToolLoader
│   ├── loader.py        # NacosToolLoader — 核心加载逻辑
│   ├── registry.py      # Tool 注册中心（缓存已注册 Tools）
│   └── base.py          # 基础工具类
├── agent/               # 新增：Agent 管理
│   ├── __init__.py
│   ├── manager.py       # AgentManager — 创建和管理 Agent 实例
│   └── cli.py           # CLI 入口（命令行模式）
api/
├── main.py              # 修改：新增 agent 相关端点
├── routes.py            # 修改：新增 chat/tools 路由
└── schemas.py           # 修改：新增 Agent 请求/响应 schema
```

## 6. 实现步骤（分阶段）

### Phase 1：基础集成（Tool 加载）
- [ ] 新建 `nacos_skill_client/tools/loader.py` — NacosToolLoader
- [ ] 新建 `nacos_skill_client/tools/registry.py` — Tool 注册中心
- [ ] 配置新增 `agent` 配置项
- [ ] 最小化测试：单个 Skill 注册为 Tool 并能被 LangChain 调用

### Phase 2：Agent 管理器
- [ ] 新建 `nacos_skill_client/agent/manager.py` — AgentManager
- [ ] 支持多 LLM provider（OpenAI/Anthropic/local）
- [ ] 支持 Tool Calling 和 ReAct 两种 Agent 类型
- [ ] 多 Skill 注册为 Tools，Agent 自动选择

### Phase 3：API 端点
- [ ] `POST /api/v1/chat` — Agent 对话端点
- [ ] `GET /api/v1/skills/tools` — Tools 列表端点
- [ ] `POST /api/v1/skills/tools/reload` — 重新加载端点
- [ ] 流式响应支持（SSE）

### Phase 4：高级功能
- [ ] 缓存优化 — metadata 本地缓存
- [ ] CLI 工具 — `nacos-agent` 命令行对话
- [ ] 多轮对话状态管理
- [ ] 性能优化 — 并发加载 Tools

## 7. 配置变更

在 `config.py` 的 `Config` 类中新增：

```python
class AgentConfig(BaseModel):
    enabled: bool = Field(default=False)
    llm_provider: str = Field(default="openai")
    model_name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_iterations: int = Field(default=10)
    max_skills_to_load: int = Field(default=50)
    agent_type: str = Field(default="tool-calling")

class Config(BaseSettings):
    # ... 现有配置不变 ...
    agent: AgentConfig = Field(default_factory=AgentConfig)
```

新增配置示例（`config/default.yaml`）：

```yaml
agent:
  enabled: true
  llm_provider: openai
  model_name: gpt-4o-mini
  temperature: 0.0
  max_iterations: 10
  max_skills_to_load: 50
  agent_type: tool-calling
```

## 8. 测试策略

- `tests/test_tools_loader.py` — 测试 Tool 加载逻辑
- `tests/test_agent_manager.py` — 测试 Agent 管理器
- `tests/test_routes_chat.py` — 测试 chat 端点
- 复用现有 Nacos mock fixtures
- 测试覆盖率目标：tools/agent/ 模块 ≥ 80%

## 9. 关键决策

1. **LangChain 为可选依赖**：`pip install nacos-skill-client[agent]`
2. **Agent 默认关闭**：`agent.enabled = false`，不影响现有 API
3. **Tool Calling 优先**：原生支持 tool_call 的模型体验最好
4. **复用 SkillCache**：不引入新的缓存机制
5. **动态注册**：Skills 从 Nacos 动态加载，不硬编码
