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


def _check_admin(token: str, expected: str) -> bool:
    """Return True only when both values are non-empty and equal.

    Used to gate the manual refresh button to the代表 (admin).
    Token comes from URL query param ``?admin=...`` and is compared
    against ``st.secrets["admin_token"]`` (set in Streamlit Cloud Secrets).
    """
    return bool(token) and bool(expected) and token == expected


def _get_admin_token_from_secrets() -> str:
    """Safely read ``admin_token`` from Streamlit Secrets.

    Returns empty string if no secrets file is present (e.g., in tests),
    so the function never raises.
    """
    try:
        return str(st.secrets.get("admin_token", ""))
    except Exception:  # noqa: BLE001 — secrets.toml may be absent in dev/CI
        return ""


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
    st.caption("AIニュースフィード — Hacker News + HuggingFace論文 + HN RSS")

    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = datetime.now()

    # 管理者判定: URLパラメータ ?admin=token と Streamlit Secrets の admin_token を照合
    # Secrets の設定方法: https://share.streamlit.io/ → アプリの Settings → Secrets
    #   admin_token = "32文字のランダム英数字"
    # 一般ユーザー（トークンなし）には更新ボタンを出さず、読み取り専用モードにする。
    _token = st.query_params.get("admin", "")
    _is_admin = _check_admin(_token, _get_admin_token_from_secrets())

    with st.sidebar:
        st.header("操作")
        st.write(
            f"最終更新: {st.session_state['last_refresh'].strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if _is_admin:
            force_refresh = st.button("更新", use_container_width=True)
            st.caption("キャッシュ有効期限: 30分")
        else:
            force_refresh = False
            st.caption("読み取り専用モード(キャッシュ有効期限: 30分)")

    if force_refresh:
        st.session_state["last_refresh"] = datetime.now()
        with st.spinner("最新情報を取得中..."):
            data, errors = _load_data(force_refresh=True)
        st.toast("更新完了", icon="✅")
    else:
        data, errors = _load_data(force_refresh=False)

    for err in errors:
        st.error(err)

    tab_hn, tab_papers, tab_rss = st.tabs(["Hacker News", "HuggingFace論文", "HN RSS"])

    with tab_hn:
        _render_tab(
            "Hacker News(AI関連・スコア50以上)",
            data.get("hn", []),
            apply_filter=True,
            empty_message="現在、HNにAI関連の記事はありません。",
        )

    with tab_papers:
        _render_tab(
            "HuggingFace 日次論文",
            data.get("hf_papers", []),
            apply_filter=False,
            empty_message="本日の論文はまだありません。",
        )

    with tab_rss:
        _render_tab(
            "HN RSS(AIキーワード)",
            data.get("rss", []),
            apply_filter=True,
            empty_message="RSSフィードにAI関連の記事はありません。",
        )


if __name__ == "__main__":
    main()
