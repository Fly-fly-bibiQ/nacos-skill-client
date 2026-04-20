#!/usr/bin/env python3
"""Skill 自动路由示例。

核心流程：
  1. 从 Nacos 获取所有可用 Skills（名称 + 描述）
  2. 将 Skills 信息 + 用户问题发给 LLM，让 LLM 判断应使用哪个 Skill
  3. 下载对应 Skill 的 SKILL.md 内容
  4. 将 SKILL.md 指令 + 用户问题再次发给 LLM，得到最终回复

用法：
  python auto_skill_router.py                     # 使用默认测试问题
  python auto_skill_router.py "帮我翻译这段文本：Hello"  # 自定义问题
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from nacos_skill_client import NacosSkillClient


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

NACOS_SERVER_ADDR: str = "http://192.168.1.118:8002"
NACOS_API_ADDR: str = "http://192.168.1.118:8848"
NACOS_USERNAME: str = "nacos"
NACOS_PASSWORD: str = "nacos"

LLM_BASE_URL: str = "http://192.168.1.118:8000/v1"
LLM_MODEL: str = "Qwen3.6-35B-A3B-FP8"
LLM_API_KEY: str = "dummy"  # 本地模型通常不需要真实 key


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #


@dataclass
class SkillInfo:
    """简化的 Skill 信息，用于发送给 LLM。"""

    name: str
    description: str
    version: str | None = None
    labels: dict[str, str] | None = None


@dataclass
class RouteResult:
    """LLM 路由结果。"""

    skill_name: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """转换为字典，方便 JSON 序列化。"""
        return {
            "skill_name": self.skill_name,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #


def build_skills_list(skills: list[SkillInfo]) -> str:
    """将 Skills 列表格式化为 LLM 可读的文本。"""
    if not skills:
        return "（暂无可用 Skill）"
    lines = [f"共 {len(skills)} 个可用 Skill："]
    for i, s in enumerate(skills, 1):
        labels = f" | 标签: {s.labels}" if s.labels else ""
        version = f" [{s.version}]" if s.version else ""
        lines.append(f"  {i}. {s.name}{version}: {s.description}{labels}")
    return "\n".join(lines)


def safe_replace(template: str, **kw: str) -> str:
    """安全替换模板变量，避免 KeyError（当值中包含 { 时）。"""
    result = template
    for k, v in kw.items():
        placeholder = f"{{{{{k}}}}}"
        result = result.replace(placeholder, str(v))
    return result


def parse_route_response(text: str) -> RouteResult:
    """解析 LLM 返回的 JSON 路由结果。"""
    # 尝试提取 JSON（可能包裹在 ```json ... ``` 中）
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else lines[1] if len(lines) > 1 else ""
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试用正则提取 JSON 对象
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                raise ValueError(f"无法解析 LLM 返回: {text[:200]}")
        else:
            raise ValueError(f"无法解析 LLM 返回: {text[:200]}")

    # 兼容 skill / skill_name 两种字段名
    skill_name = data.get("skill_name") or data.get("skill")
    reason = data.get("reason", "未提供原因")
    return RouteResult(skill_name=skill_name, reason=reason)


def call_llm(
    client: OpenAI,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """调用 LLM API 并返回文本内容。"""
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# --------------------------------------------------------------------------- #
# 核心逻辑
# --------------------------------------------------------------------------- #


def fetch_all_skills(client: NacosSkillClient) -> list[SkillInfo]:
    """从 Nacos 获取所有可用 Skills。"""
    all_skills: list[SkillInfo] = []
    page_size = 100  # 每次尽可能多取
    page_no = 1

    while True:
        result = client.list_skills(page_no=page_no, page_size=page_size)
        for item in result.page_items:
            all_skills.append(SkillInfo(
                name=item.name,
                description=item.description,
                version=item.editing_version,
                labels=item.labels if item.labels else None,
            ))
        if page_no >= result.pages_available:
            break
        page_no += 1

    return all_skills


def route_skill(
    llm_client: OpenAI,
    skills: list[SkillInfo],
    user_query: str,
) -> RouteResult:
    """让 LLM 根据 Skills 列表判断应使用哪个 Skill。"""
    skills_list_text = build_skills_list(skills)

    prompt = (
        "你是一个 Skill 路由助手。\n"
        "\n"
        "你的任务：\n"
        "1. 分析用户的意图\n"
        "2. 从可用的 Skill 列表中找出最匹配的一个\n"
        "3. 如果不需要任何 Skill 也能回答问题，返回 null\n"
        "\n"
        '请严格按照以下 JSON 格式返回，不要包含任何 Markdown 代码块标记、'
        '不要包含反引号、不要包含任何其他文字：\n'
        '{"skill_name": null, "reason": "简要说明原因"}\n'
        "\n"
        "注意：字段名必须是 skill_name 和 reason，不能是 skill 或其他名称。\n"
        "\n"
        "可用的 Skill 列表：\n"
        f"{skills_list_text}\n"
        "\n"
        f"用户问题：\n"
        f"{user_query}\n"
    )

    messages = [
        {"role": "system", "content": "你是一个 Skill 路由助手。只返回 JSON，不要包含 Markdown 代码块标记。"},
        {"role": "user", "content": prompt},
    ]

    response_text = call_llm(llm_client, messages)
    return parse_route_response(response_text)


def get_skill_md_content(
    client: NacosSkillClient,
    skill_name: str,
) -> str:
    """获取 Skill 的指令文件内容（SKILL.md / AGENTS.md / SOUL.md）。

    尝试优先级：
    1. SKILL.md
    2. AGENTS.md
    3. SOUL.md
    """
    try:
        detail = client.get_skill_detail(skill_name)
    except Exception as exc:
        raise RuntimeError(f"获取 Skill 详情失败: {skill_name}: {exc}") from exc

    if not detail.versions:
        raise RuntimeError(f"Skill 没有可用版本: {skill_name}")

    # 优先使用 editing_version，否则用第一个版本
    version = detail.editing_version or (detail.versions[0].version if detail.versions else None)
    if not version:
        raise RuntimeError(f"Skill 没有可用版本: {skill_name}")

    # 按优先级尝试获取指令文件
    file_fetchers = [
        ("SKILL.md", lambda: client.get_skill_md(skill_name, version)),
        ("AGENTS.md", lambda: client.get_agents_md(skill_name, version)),
        ("SOUL.md", lambda: client.get_soul_md(skill_name, version)),
    ]

    last_exc: Exception | None = None
    for file_label, fetcher in file_fetchers:
        try:
            content = fetcher()
            return content  # 找到第一个可用的
        except Exception as exc:
            last_exc = exc
            continue

    # 全部失败，尝试直接获取版本详情看有哪些文件
    available = []
    try:
        version_detail = client.get_skill_version_detail(skill_name, version)
        available = list(version_detail.resource.keys())
    except Exception:
        pass

    avail_str = f"（可用资源: {', '.join(available)}）" if available else ""
    raise RuntimeError(
        f"Skill 没有指令文件: {skill_name}/{version}: SKILL.md/AGENTS.md/SOUL.md 均不存在 {avail_str}"
    ) from last_exc


def execute_with_skill(
    llm_client: OpenAI,
    skill_name: str,
    skill_md: str,
    user_query: str,
    file_label: str = "SKILL.md",
) -> str:
    """使用 Skill 的指令文件 + LLM 生成最终回复。

    Args:
        skill_name: Skill 名称。
        skill_md: 指令文件内容。
        user_query: 用户问题。
        file_label: 指令文件标签（SKILL.md / AGENTS.md / SOUL.md）。
    """
    prompt = (
        f"下面的内容是 {skill_name} 的指令文件（{file_label}），请按照以上指令，帮助用户解决问题。\n"
        "\n"
        f"--- 指令开始 ---\n"
        f"{skill_md}\n"
        f"--- 指令结束 ---\n"
        "\n"
        f"用户问题：\n"
        f"{user_query}\n"
    )

    messages = [
        {"role": "system", "content": "你是一个 AI 助手，请严格按照以下 Skill 指令帮助用户解决问题。"},
        {"role": "user", "content": prompt},
    ]

    return call_llm(llm_client, messages)


def auto_route_and_execute(
    user_query: str,
) -> dict[str, Any]:
    """完整的路由 + 执行流程。

    Returns:
        包含路由结果和最终回复的字典。
    """
    # 1. 从 Nacos 获取所有 Skills
    with NacosSkillClient(
        server_addr=NACOS_SERVER_ADDR,
        api_addr=NACOS_API_ADDR,
        username=NACOS_USERNAME,
        password=NACOS_PASSWORD,
    ) as nacos_client:
        print(f"📡 正在从 Nacos 获取 Skills...")
        skills = fetch_all_skills(nacos_client)
        print(f"✅ 获取到 {len(skills)} 个可用 Skill")

        # 2. 路由：让 LLM 判断用哪个 Skill
        llm_client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        print(f"\n🧠 正在分析用户意图...")
        route_result = route_skill(llm_client, skills, user_query)

        print(f"\n📌 路由结果:")
        print(f"   Skill: {route_result.skill_name or '(无需 Skill)'}")
        print(f"   原因: {route_result.reason}")

        # 3. 如果需要 Skill，获取指令文件并执行
        if route_result.skill_name:
            print(f"\n📥 正在下载 Skill '{route_result.skill_name}' 的指令文件...")
            try:
                skill_md = get_skill_md_content(nacos_client, route_result.skill_name)
                print(f"✅ 指令文件获取成功 ({len(skill_md)} 字符)")
                print(f"\n🤖 正在使用 Skill 生成回复...")
                final_answer = execute_with_skill(llm_client, route_result.skill_name, skill_md, user_query)
            except RuntimeError as exc:
                final_answer = f"⚠️ 获取 Skill 内容失败: {exc}"
        else:
            # 不需要 Skill，直接让 LLM 回答
            print(f"\n🤖 无需 Skill，直接用 LLM 回答...")
            messages = [
                {"role": "user", "content": user_query},
            ]
            final_answer = call_llm(llm_client, messages)

        return {
            "query": user_query,
            "route": route_result.to_dict(),
            "answer": final_answer,
        }


# --------------------------------------------------------------------------- #
# 演示
# --------------------------------------------------------------------------- #


DEMO_QUESTIONS: list[str] = [
    "帮我翻译一段文本：The quick brown fox jumps over the lazy dog.",
    "帮我写一个 Python 的 HTTP 服务器",
    "今天北京天气怎么样？",
    "解释一下 Transformer 模型的注意力机制",
    "帮我写一段 HTML + CSS 的响应式布局",
]


def run_demo(questions: list[str] | None = None) -> None:
    """运行演示：逐个测试预设问题。"""
    questions = questions or DEMO_QUESTIONS

    for i, query in enumerate(questions, 1):
        print("\n" + "=" * 80)
        print(f"  测试 {i}/{len(questions)}: {query}")
        print("=" * 80)
        try:
            result = auto_route_and_execute(query)
            print(f"\n💬 最终回复:")
            print("-" * 40)
            print(result["answer"][:1500])  # 截断过长回复
            print("-" * 40)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"\n❌ 执行失败: {exc}")
        print()


def run_interactive() -> None:
    """交互式模式：用户输入问题，自动路由。"""
    print("=" * 80)
    print("  Skill 自动路由 - 交互式模式")
    print("  输入问题，按 Enter 开始。输入 'quit' 退出。")
    print("=" * 80)

    while True:
        query = input("\n请输入你的问题: ").strip()
        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("再见！👋")
            break

        print(f"\n📝 你的问题: {query}")
        print()
        try:
            result = auto_route_and_execute(query)
            print(f"\n📌 路由结果: Skill={result['route'].skill_name}, Reason={result['route'].reason}")
            print(f"\n💬 回复:")
            print("-" * 40)
            print(result["answer"][:2000])
            print("-" * 40)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"\n❌ 执行失败: {exc}")


if __name__ == "__main__":
    # 支持命令行参数传入问题
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        result = auto_route_and_execute(query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Skill 自动路由 - 演示模式")
        run_demo()
