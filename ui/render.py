"""Streamlit rendering helpers for article cards."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from translator import translate_title

from .safety import is_safe_url, sanitize_markdown_text


_SOURCE_LABELS = {
    "hn": "Hacker News",
    "hf_papers": "HuggingFace論文",
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

    タイトルは Claude Haiku で日本語訳し、原題も小さく併記する。
    URL が安全(http/https)なら Markdown リンクとして描画し、そうでなければ
    プレーンテキスト扱い(``javascript:`` などのスキームを描画させない)。
    """
    raw_title = article.get("title") or "(no title)"
    raw_url = article.get("url")
    score = article.get("score")
    source_key = article.get("source", "")
    source_label = _SOURCE_LABELS.get(source_key, source_key or "unknown")
    timestamp = _format_time(article)

    # 翻訳タイトル(失敗時は原題に自動フォールバック)。
    translated_title = translate_title(raw_title)

    # Markdown 注入対策(タイトルから [, ], (, ) を除去)。
    safe_title = sanitize_markdown_text(translated_title) or "(no title)"
    safe_original = sanitize_markdown_text(raw_title)

    # スキーム許可リストを通過した URL のみリンク化する。
    if is_safe_url(raw_url):
        st.markdown(f"#### [{safe_title}]({raw_url})")
    else:
        st.markdown(f"#### {safe_title}")

    # 翻訳が原題と異なるときだけ原題を併記(同一なら冗長なのでスキップ)。
    if translated_title != raw_title and safe_original:
        st.caption(f"原題: {safe_original}")

    caption_parts: list[str] = []
    if score is not None:
        caption_parts.append(f"スコア: {score}")
    caption_parts.append(f"出典: {source_label}")
    if timestamp:
        caption_parts.append(timestamp)
    by = article.get("by")
    if by:
        caption_parts.append(f"投稿者: {by}")

    st.caption("  |  ".join(caption_parts))

    summary = article.get("summary")
    if summary:
        snippet = summary if len(summary) <= 280 else summary[:280].rstrip() + "..."
        st.write(snippet)

    st.divider()


__all__ = ["render_article_card"]
