#!/usr/bin/env python3
"""Nacos Skill Registry 客户端使用示例。"""

from __future__ import annotations

from nacos_skill_client import NacosSkillClient


def main() -> None:
    # 创建客户端（使用 with 语句自动关闭连接）
    with NacosSkillClient(
        server_addr="http://192.168.1.118:8002",
        api_addr="http://192.168.1.118:8848",
        username="nacos",
        password="nacos",
        namespace_id="public",
    ) as client:
        print("=" * 70)
        print("1. 列出 Skills（前 10 个）")
        print("=" * 70)
        result = client.list_skills(page_size=10)
        print(f"总计 {result.total_count} 个 Skills, 共 {result.pages_available} 页")
        print()
        for item in result.page_items:
            status = "✅" if item.enable else "❌"
            print(f"  {status} {item.name}")
            print(f"     {item.description[:80]}")
            print(f"     标签: {item.biz_tags} | 来源: {item.from_source}")
        print()

        # 搜索 Skills
        print("=" * 70)
        print("2. 搜索 Skills（关键词: '测试'）")
        print("=" * 70)
        result = client.search_skills(keyword="测试", page_size=5)
        print(f"找到 {result.total_count} 个匹配结果")
        for item in result.page_items:
            print(f"  - {item.name}: {item.description[:60]}")
        print()

        # 获取 Skill 详情
        print("=" * 70)
        print("3. 获取 Skill 详情（'提示词工程师'）")
        print("=" * 70)
        detail = client.get_skill_detail("提示词工程师")
        print(f"名称: {detail.name}")
        print(f"Scope: {detail.scope}")
        print(f"Enable: {detail.enable}")
        print(f"标签: {detail.labels}")
        print(f"版本列表:")
        for v in detail.versions:
            print(f"  - {v.version} ({v.status}) by {v.author}")
            print(f"    {v.description[:80]}")
        print()

        # 获取 SKILL.md 内容
        print("=" * 70)
        print("4. 获取 Skill 版本详情（'提示词工程师' v1）")
        print("=" * 70)
        version_detail = client.get_skill_version_detail("提示词工程师", "v1")
        print(f"Content 长度: {len(version_detail.content)} 字符")
        print(f"Content preview:")
        print(version_detail.content[:500])
        print()
        print(f"Resource 文件列表: {list(version_detail.resource.keys())}")
        print()

        # 获取单个资源文件
        print("=" * 70)
        print("5. 获取 AGENTS.md 文件内容")
        print("=" * 70)
        agents_md = client.get_agents_md("提示词工程师", "v1")
        print(f"AGENTS.md 长度: {len(agents_md)} 字符")
        print(agents_md[:800])
        print()

        # 获取 SKILL.md
        print("=" * 70)
        print("6. 获取 SKILL.md 文件内容")
        print("=" * 70)
        try:
            skill_md = client.get_skill_md("提示词工程师", "v1")
            print(f"SKILL.md 长度: {len(skill_md)} 字符")
            print(skill_md[:500] if skill_md else "(空)")
        except Exception as e:
            print(f"SKILL.md 不存在: {e}")
        print()

        # 获取 SOUL.md
        print("=" * 70)
        print("7. 获取 SOUL.md 文件内容")
        print("=" * 70)
        try:
            soul_md = client.get_soul_md("提示词工程师", "v1")
            print(f"SOUL.md 长度: {len(soul_md)} 字符")
            print(soul_md[:500] if soul_md else "(空)")
        except Exception as e:
            print(f"SOUL.md 不存在: {e}")

        print()
        print("=" * 70)
        print("所有示例执行完成！")
        print("=" * 70)


if __name__ == "__main__":
    main()
