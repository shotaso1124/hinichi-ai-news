"""Tests for the URL/Markdown sanitization helpers in ``ui/safety.py``.

These guard the XSS fix that gates external URLs before they are rendered as
Markdown links in the Streamlit cards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# is_safe_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1",
        "HTTPS://EXAMPLE.COM",  # case-insensitive scheme
        "https://huggingface.co/papers/2401.00001",
    ],
)
def test_is_safe_url_accepts_http_and_https(url):
    from ui.safety import is_safe_url

    assert is_safe_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        " javascript:alert(1)",  # leading whitespace must not bypass the check
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "ftp://example.com",
        "//example.com",  # protocol-relative
        "/relative/path",
        "",
        "#",
        "vbscript:msgbox(1)",
    ],
)
def test_is_safe_url_rejects_dangerous_or_relative(url):
    from ui.safety import is_safe_url

    assert is_safe_url(url) is False


@pytest.mark.parametrize("url", [None, 123, [], {}, object()])
def test_is_safe_url_rejects_non_strings(url):
    from ui.safety import is_safe_url

    assert is_safe_url(url) is False


# ---------------------------------------------------------------------------
# sanitize_markdown_text
# ---------------------------------------------------------------------------


def test_sanitize_markdown_text_strips_link_chars():
    from ui.safety import sanitize_markdown_text

    # Classic injection attempt: closing the safe label and opening a hostile link.
    payload = "Foo](javascript:alert(1))"
    cleaned = sanitize_markdown_text(payload)
    assert "[" not in cleaned
    assert "]" not in cleaned
    assert "(" not in cleaned
    assert ")" not in cleaned


def test_sanitize_markdown_text_passthrough_safe_text():
    from ui.safety import sanitize_markdown_text

    assert sanitize_markdown_text("Hello, world!") == "Hello, world!"
    assert sanitize_markdown_text("日本語タイトル") == "日本語タイトル"


def test_sanitize_markdown_text_handles_none():
    from ui.safety import sanitize_markdown_text

    assert sanitize_markdown_text(None) == ""


def test_sanitize_markdown_text_handles_non_string():
    from ui.safety import sanitize_markdown_text

    assert sanitize_markdown_text(42) == "42"
