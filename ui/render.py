"""Streamlit rendering helpers for article cards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from .safety import is_safe_url, sanitize_markdown_text


_SOURCE_LABELS = {
    "hn": "Hacker News",
    "hf_papers": "HuggingFace Papers",
    "rss": "HN RSS",
}


def _format_time(article: dict[str, Any]) -> str | None:
    """Best-effort human-friendly timestamp for the card caption."""
    raw_time = article.get("time")
    if isinstance(raw_time, (int, float)):
        try:
            dt = datetime.fromtimestamp(raw_time, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except (OverflowError, OSError, ValueError):
            return None

    for key in ("published_at", "published"):
        value = article.get(key)
        if value:
            return str(value)
    return None


def render_article_card(article: dict[str, Any]) -> None:
    """Render a single article as a Streamlit card.

    The title is rendered as a markdown link (opens in a new tab from the
    user's browser), and a caption shows score, source and timestamp.
    """
    raw_title = article.get("title") or "(no title)"
    raw_url = article.get("url")
    score = article.get("score")
    source_key = article.get("source", "")
    source_label = _SOURCE_LABELS.get(source_key, source_key or "unknown")
    timestamp = _format_time(article)

    # Sanitize title against Markdown injection (e.g. "Foo](javascript:...)").
    safe_title = sanitize_markdown_text(raw_title) or "(no title)"
    # Render as a link only when the URL passes the strict scheme allowlist;
    # otherwise show plain text so a hostile ``javascript:`` URL never reaches
    # the rendered HTML.
    if is_safe_url(raw_url):
        st.markdown(f"#### [{safe_title}]({raw_url})")
    else:
        st.markdown(f"#### {safe_title}")

    caption_parts: list[str] = []
    if score is not None:
        caption_parts.append(f"Score: {score}")
    caption_parts.append(f"Source: {source_label}")
    if timestamp:
        caption_parts.append(timestamp)
    by = article.get("by")
    if by:
        caption_parts.append(f"by {by}")

    st.caption("  |  ".join(caption_parts))

    summary = article.get("summary")
    if summary:
        snippet = summary if len(summary) <= 280 else summary[:280].rstrip() + "..."
        st.write(snippet)

    st.divider()


__all__ = ["render_article_card"]
