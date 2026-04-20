"""测试 _extract_body 函数（从 Markdown 中提取 body，去除 frontmatter）。"""

from nacos_skill_client.client import _extract_body


class TestExtractBody:
    """测试 _extract_body 函数。"""

    def test_with_frontmatter(self):
        content = '''---
name: test-skill
description: A test skill
---

# Title

This is the body.
'''
        result = _extract_body(content)
        assert "name: test-skill" not in result
        assert "# Title" in result
        assert "This is the body." in result

    def test_without_frontmatter(self):
        content = "# Title\n\nJust body content."
        result = _extract_body(content)
        assert result == "# Title\n\nJust body content."

    def test_empty_content(self):
        result = _extract_body("")
        assert result == ""

    def test_none_content(self):
        result = _extract_body(None)
        assert result == ""

    def test_multiline_body(self):
        content = '''---
name: multi
description: test
---

# Section 1
Line 1

## Section 2
Line 2 with **bold**

```python
code here
```
'''
        result = _extract_body(content)
        assert "# Section 1" in result
        assert "Line 1" in result
        assert "name: multi" not in result
