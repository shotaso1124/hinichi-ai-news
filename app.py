"""Streamlit entry point for the ひにち AI News app (Phase 1 MVP)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from fetchers import fetch_all
from ui.filters import filter_articles
from ui.render import render_article_card

load_dotenv()
GA4_ID = os.getenv("GA4_MEASUREMENT_ID", "")


st.set_page_config(page_title="ひにち AI News", layout="wide")

if GA4_ID and GA4_ID != "G-XXXXXXXXXX":
    GA4_TAG = f"""
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{GA4_ID}');
    </script>
    """
    components.html(GA4_TAG, height=0)


def _load_data(force_refresh: bool) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Run fetch_all and capture per-source errors."""
    errors: list[str] = []
    try:
        data = fetch_all(force_refresh=force_refresh)
    except Exception as exc:  # noqa: BLE001 — top-level fallback for UI
        errors.append(f"fetch_all failed: {exc}")
        data = {"hn": [], "hf_papers": [], "rss": []}
    return data, errors


def _render_tab(
    title: str,
    articles: list[dict[str, Any]],
    *,
    apply_filter: bool,
    empty_message: str,
) -> None:
    """Render a tab. ``apply_filter`` controls whether the AI keyword filter runs."""
    st.subheader(title)
    visible = filter_articles(articles) if apply_filter else articles
    if not visible:
        st.info(empty_message)
        return
    for article in visible:
        render_article_card(article)


def main() -> None:
    st.title("ひにち AI News")
    st.caption("Personal AI news feed — Hacker News + HuggingFace Daily Papers + HN RSS")

    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = datetime.now()

    with st.sidebar:
        st.header("Controls")
        st.write(
            f"Last update: {st.session_state['last_refresh'].strftime('%Y-%m-%d %H:%M:%S')}"
        )
        force_refresh = st.button("Refresh", use_container_width=True)
        st.caption("Cache TTL: 30 minutes")

    if force_refresh:
        st.session_state["last_refresh"] = datetime.now()

    data, errors = _load_data(force_refresh=force_refresh)

    for err in errors:
        st.error(err)

    tab_hn, tab_papers, tab_rss = st.tabs(["HN Stories", "HF Papers", "HN RSS"])

    with tab_hn:
        _render_tab(
            "Hacker News (AI-filtered, score >= 50)",
            data.get("hn", []),
            apply_filter=True,
            empty_message="No AI-related stories on HN right now.",
        )

    with tab_papers:
        _render_tab(
            "HuggingFace Daily Papers",
            data.get("hf_papers", []),
            apply_filter=False,
            empty_message="No papers available for today yet.",
        )

    with tab_rss:
        _render_tab(
            "HN RSS (AI keyword)",
            data.get("rss", []),
            apply_filter=True,
            empty_message="No AI-related items in the RSS feed.",
        )


if __name__ == "__main__":
    main()
