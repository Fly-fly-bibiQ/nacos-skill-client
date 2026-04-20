"""测试工具函数。"""

import pytest

from nacos_skill_client.utils import build_prompt, extract_frontmatter_content, extract_body


class TestBuildPrompt:
    def test_builds_messages(self):
        msgs = build_prompt("You are helpful", "Hello")
        assert len(msgs) == 2
        assert msgs[0] == {"role": "system", "content": "You are helpful"}
        assert msgs[1] == {"role": "user", "content": "Hello"}


class TestFrontmatter:
    def test_extract_frontmatter(self):
        content = "---\nname: test\n\ndescription: A test\n---\n\nBody here"
        result = extract_frontmatter_content(content)
        assert result["name"] == "test"
        assert result["description"] == "A test"

    def test_no_frontmatter(self):
        result = extract_frontmatter_content("no frontmatter here")
        assert result == {}

    def test_empty(self):
        result = extract_frontmatter_content("")
        assert result == {}


class TestExtractBody:
    def test_with_frontmatter(self):
        content = "---\nname: test\n---\n\nHello world"
        result = extract_body(content)
        assert result == "Hello world"

    def test_without_frontmatter(self):
        content = "Just plain text"
        result = extract_body(content)
        assert result == "Just plain text"

    def test_empty(self):
        result = extract_body("")
        assert result == ""
