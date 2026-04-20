"""LangGraph Agent — 流式 Skill 路由执行。

基于 LangGraph StateGraph 构建 Skill 路由 Agent 图：

Graph 流程:
  START → discover → route → (activate | execute_direct) → END

每个节点:
  - discover: 从 Nacos 发现可用 Skills（元数据）
  - route: LLM 路由决策，选择最匹配的 Skill
  - activate: 加载 Skill 的指令文件
  - execute: 使用 Skill 指令 + 用户问题调用 LLM 流式输出
  - execute_direct: 无 Skill 时直接 LLM 调用

SSE 事件流:
  discovered → skill_selected / no_skill → instruction_loaded → content* → done

使用方式 (FastAPI SSE):
    from agent.stream import stream_agent_response

    def endpoint():
        for event in stream_agent_response(user_msg, client, config, llm, router):
            yield event
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph as LangGraphCompiled
from langgraph.types import Send

logger = logging.getLogger(__name__)


# ── State ────────────────────────────────────────────────────────────────────

class AgentState(dict):
    """Agent 状态（dict 子类的最小状态模型）。"""
    pass


# ── Node 实现 ────────────────────────────────────────────────────────────────

def discover(state: AgentState, client: Any, config: Any) -> AgentState:
    """从 Nacos 发现可用 Skills。"""
    items = client.get_all_skills()[: config.router.max_skills_for_routing]
    logger.info("graph: discovered %d skills", len(items))
    return AgentState({"_skills": items})


def route(state: AgentState, router: Any, user_message: str) -> AgentState:
    """LLM 路由，决定选择哪个 Skill。"""
    skills = state.get("_skills", [])
    result = router.route(skills, user_message)
    logger.info("graph: route skill=%s, reason=%s", result.skill_name or "N/A", result.reason[:80])
    return AgentState({
        "_route_skill_name": result.skill_name,
        "_route_reason": result.reason,
    })


def activate(state: AgentState, client: Any, config: Any) -> AgentState:
    """加载选中 Skill 的指令文件。"""
    skill_name = state["_route_skill_name"]
    priority = config.router.instruction_file_priority

    file_label, instruction = "", ""

    # 缓存优先
    if client.cache and client.cache.has_skill(skill_name):
        file_label, instruction = client.cache.get_skill_file(
            skill_name, priority[0],
        )

    # Nacos 下载
    if not instruction:
        file_label, instruction = client.get_instruction_file(
            skill_name, "", priority=priority,
        )

    # 截断过长指令
    max_len = 8000
    if len(instruction) > max_len:
        instruction = instruction[:max_len] + f"\n\n...(truncated, total {len(instruction)} chars)"

    logger.info("graph: instruction loaded (%s, %d chars)", file_label, len(instruction))
    return AgentState({
        "_instruction": instruction,
        "_instruction_file": file_label,
    })


def execute_with_skill(
    state: AgentState,
    llm: Any,
    config: Any,
) -> AgentState:
    """使用 Skill 指令调 LLM 流式输出（不收集结果，只流式 yield）。"""
    # 这个节点不收集结果，由调用方处理流式
    # 返回空状态，让图走到 END
    return AgentState({})


def execute_direct(
    state: AgentState,
    llm: Any,
    config: Any,
) -> AgentState:
    """无 Skill 时直接调 LLM（不收集结果，只流式 yield）。"""
    return AgentState({})


def should_activate(state: AgentState):
    """路由条件边：有选中的 Skill 就激活，否则直接执行。"""
    skill_name = state.get("_route_skill_name")
    return "activate" if skill_name else "execute_direct"


def end_point(state: AgentState) -> AgentState:
    """图的终结节点。"""
    return state


# ── Graph 构建 ───────────────────────────────────────────────────────────────

def build_graph() -> CompiledGraph:
    """构建并编译 LangGraph StateGraph。"""
    graph = StateGraph(state_schema=AgentState)

    # 添加节点
    graph.add_node("discover", discover)
    graph.add_node("route", route)
    graph.add_node("activate", activate)
    graph.add_node("execute_with_skill", execute_with_skill)
    graph.add_node("execute_direct", execute_direct)
    graph.add_node("end", end_point)

    # 添加边
    graph.add_edge(START, "discover")
    graph.add_edge("discover", "route")

    # 条件边
    graph.add_conditional_edges(
        "route",
        should_activate,
        {
            "activate": "activate",
            "execute_direct": "execute_direct",
        },
    )

    graph.add_edge("activate", "execute_with_skill")
    graph.add_edge("execute_direct", "end")
    graph.add_edge("execute_with_skill", "end")

    return graph.compile()


# ── 流式 SSE 生成器 ──────────────────────────────────────────────────────────

def stream_agent_response(
    user_message: str,
    client: Any,
    config: Any,
    llm: Any,
    router: Any,
) -> Iterator[dict[str, Any]]:
    """Agent 流式响应生成器。

    将 LangGraph StateGraph 的节点流程映射为 SSE 事件。

    Args:
        user_message: 用户输入消息
        client: NacosSkillClient 实例
        config: Config 实例
        llm: LangChain ChatModel (stream 接口)
        router: SkillRouter 实例

    Yields:
        {"event": str, "data": str} SSE 事件
    """
    # 编译图（含依赖注入）
    graph = _build_injected_graph(client, config, llm, router)

    # ── 使用 LangGraph stream，stream_mode="updates" 获取节点输出 ──
    # stream_mode="updates" 会在每个节点完成时 emit {node_name: {updated_fields}}

    initial_state = AgentState({"_user_message": user_message})

    # Step 1: Discover（独立于图，提前 emit）
    skills_state = discover(initial_state, client, config)
    skills = skills_state.get("_skills", [])
    logger.info("stream: discovered %d skills", len(skills))
    yield {"event": "discovered", "data": json.dumps({
        "count": len(skills),
        "skills": [{"name": s.name, "description": getattr(s, "description", "")}
                    for s in skills],
    }, ensure_ascii=False)}

    # Step 2: Route
    route_state = route(skills_state, router, user_message)
    skill_name = route_state.get("_route_skill_name")
    route_reason = route_state.get("_route_reason", "")
    logger.info("stream: route skill=%s, reason=%s", skill_name or "N/A", route_reason[:80])

    if skill_name:
        # ── Step 3: Activate ──
        activate_state = activate(route_state, client, config)
        file_label = activate_state.get("_instruction_file", "")
        instruction = activate_state.get("_instruction", "")

        yield {"event": "skill_selected", "data": json.dumps({
            "skill_name": skill_name,
            "reason": route_reason,
        }, ensure_ascii=False)}

        yield {"event": "instruction_loaded", "data": json.dumps({
            "file": file_label,
            "length": len(instruction),
            "skill_name": skill_name,
        }, ensure_ascii=False)}

        # ── Step 4: Execute with Skill ──
        messages = [
            SystemMessage(
                content="你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。",
            ),
            HumanMessage(
                content=(
                    f"--- Skill: {skill_name} ({file_label}) ---\n"
                    f"{instruction}\n--- 指令结束 ---\n\n"
                    f"用户问题：\n{user_message}\n"
                ),
            ),
        ]

        _stream_llm_content(messages, llm, config)
    else:
        # ── Step 3 (bypass): Direct LLM ──
        logger.info("stream: no skill matched, direct LLM call")
        yield {"event": "no_skill", "data": json.dumps({
            "reason": route_reason,
        }, ensure_ascii=False)}

        _stream_llm_content(
            [HumanMessage(content=user_message)],
            llm, config,
        )

    # ── Done ──
    for evt in _final_sse("done", json.dumps({"status": "complete"})):
        yield evt


def _build_injected_graph(
    client: Any,
    config: Any,
    llm: Any,
    router: Any,
):
    """构建带依赖注入的 LangGraph 编译图。"""
    g = StateGraph(state_schema=AgentState)

    g.add_node("discover", lambda s: discover(s, client, config))
    g.add_node("route", lambda s: route(s, router, s.get("_user_message", "")))
    g.add_node("activate", lambda s: activate(s, client, config))
    g.add_node("execute_with_skill", lambda s: execute_with_skill(s, llm, config))
    g.add_node("execute_direct", lambda s: execute_direct(s, llm, config))
    g.add_node("end", end_point)

    g.add_edge(START, "discover")
    g.add_edge("discover", "route")
    g.add_conditional_edges(
        "route",
        should_activate,
        {"activate": "activate", "execute_direct": "execute_direct"},
    )
    g.add_edge("activate", "execute_with_skill")
    g.add_edge("execute_direct", "end")
    g.add_edge("execute_with_skill", "end")

    return g.compile()


def _stream_llm_content(messages: list, llm: Any, config: Any):
    """流式调用 LLM 并 yield content chunks。"""
    resp = llm.stream(
        messages,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )
    for chunk in resp:
        if chunk.content:
            yield {"event": "content", "data": chunk.content}


def _final_sse(event: str, data: str) -> Iterator[dict[str, Any]]:
    """产生一个一次性 SSE 事件（用于 done 等单次事件）。"""
    yield {"event": event, "data": data}
