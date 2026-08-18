"""Tests for frontmatter parsing and stripping."""
from rag_mcp.ingest import parse_frontmatter, strip_frontmatter


def test_parse_frontmatter_with_yaml():
    """Parse YAML frontmatter from markdown."""
    text = """---
title: Test Document
url: https://example.com/test
tags:
  - security
  - testing
created: 2024-01-01
updated: 2024-01-15
---
# Content here
"""
    frontmatter, content = parse_frontmatter(text)
    assert frontmatter["title"] == "Test Document"
    assert frontmatter["url"] == "https://example.com/test"
    assert frontmatter["tags"] == ["security", "testing"]
    assert str(frontmatter["created"]) == "2024-01-01"
    assert str(frontmatter["updated"]) == "2024-01-15"
    assert content.strip() == "# Content here"


def test_parse_frontmatter_without_yaml():
    """Text without frontmatter returns empty dict and original content."""
    text = "# Just content\nNo frontmatter here."
    frontmatter, content = parse_frontmatter(text)
    assert frontmatter == {}
    assert content == text


def test_parse_frontmatter_empty_frontmatter():
    """Empty frontmatter block returns empty dict."""
    text = """---
---
# Content
"""
    frontmatter, content = parse_frontmatter(text)
    assert frontmatter == {}
    assert content.strip() == "# Content"


def test_parse_frontmatter_partial_fields():
    """Frontmatter with only some fields parses what's present."""
    text = """---
title: Just a title
---
Content
"""
    frontmatter, content = parse_frontmatter(text)
    assert frontmatter["title"] == "Just a title"
    assert "url" not in frontmatter
    assert content.strip() == "Content"


def test_strip_frontmatter_removes_yaml():
    """strip_frontmatter removes YAML block and returns content only."""
    text = """---
title: Test
tags:
  - a
  - b
---
# Heading
Body text
"""
    result = strip_frontmatter(text)
    assert "---" not in result
    assert "title:" not in result
    assert result.strip() == "# Heading\nBody text"


def test_strip_frontmatter_no_frontmatter():
    """strip_frontmatter returns original text if no frontmatter."""
    text = "# Heading\nBody text"
    result = strip_frontmatter(text)
    assert result == text


def test_parse_frontmatter_invalid_yaml():
    """Invalid YAML returns empty dict and treats as content."""
    text = """---
title: [unclosed
---
Content
"""
    frontmatter, content = parse_frontmatter(text)
    # Invalid YAML should be treated as no frontmatter
    assert frontmatter == {}
    assert text in content or content.strip() == text.strip()
