"""Tests for fetchers, the SQLite TTL cache, and the AI keyword filter."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the project root importable when pytest is run from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Cache: redirect AI_NEWS_CACHE_DB to a tmp file for every test
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_cache_db(monkeypatch):
    """Point the cache module at a fresh temporary SQLite file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_cache.db"
        monkeypatch.setenv("AI_NEWS_CACHE_DB", str(db_path))
        yield db_path


# ---------------------------------------------------------------------------
# store/cache.py
# ---------------------------------------------------------------------------


def test_cache_set_then_get_returns_payload(tmp_cache_db):
    from store import cache

    payload = [{"id": 1, "title": "Test"}]
    cache.set("hn", "topstories", payload, ttl_minutes=30)

    assert cache.get("hn", "topstories") == payload


def test_cache_get_missing_returns_none(tmp_cache_db):
    from store import cache

    assert cache.get("hn", "does_not_exist") is None


def test_cache_expired_returns_none(tmp_cache_db):
    from store import cache

    payload = [{"id": 1}]
    cache.set("hn", "topstories", payload, ttl_minutes=30)

    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    import sqlite3

    conn = sqlite3.connect(os.environ["AI_NEWS_CACHE_DB"])
    conn.execute(
        "UPDATE cache SET expires_at = ? WHERE source = 'hn' AND cache_key = 'topstories'",
        (expired,),
    )
    conn.commit()
    conn.close()

    assert cache.get("hn", "topstories") is None


def test_cache_upsert_replaces_existing(tmp_cache_db):
    from store import cache

    cache.set("hn", "topstories", [{"id": 1}], ttl_minutes=30)
    cache.set("hn", "topstories", [{"id": 2}], ttl_minutes=30)

    assert cache.get("hn", "topstories") == [{"id": 2}]


def test_cache_clear(tmp_cache_db):
    from store import cache

    cache.set("hn", "a", [1], ttl_minutes=30)
    cache.set("hn", "b", [2], ttl_minutes=30)
    cache.clear("hn")

    assert cache.get("hn", "a") is None
    assert cache.get("hn", "b") is None


def test_cache_corrupt_timestamp_purges_row(tmp_cache_db):
    """A row with a non-ISO ``expires_at`` is treated as expired and deleted."""
    import sqlite3

    from store import cache

    cache.set("hn", "topstories", [{"id": 1}], ttl_minutes=30)

    conn = sqlite3.connect(os.environ["AI_NEWS_CACHE_DB"])
    conn.execute(
        "UPDATE cache SET expires_at = ? WHERE source = 'hn' AND cache_key = 'topstories'",
        ("not-an-iso-timestamp",),
    )
    conn.commit()
    conn.close()

    # First call should detect the corrupt timestamp and purge.
    assert cache.get("hn", "topstories") is None

    # The row must actually be gone after the purge.
    conn = sqlite3.connect(os.environ["AI_NEWS_CACHE_DB"])
    row = conn.execute(
        "SELECT 1 FROM cache WHERE source = 'hn' AND cache_key = 'topstories'"
    ).fetchone()
    conn.close()
    assert row is None


# ---------------------------------------------------------------------------
# fetchers/hn.py
# ---------------------------------------------------------------------------


def _make_mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_hn_top_stories_filters_by_score(monkeypatch):
    """High-score items pass; sub-50 items are dropped."""
    from fetchers import hn

    items = {
        1: {"id": 1, "title": "AI breakthrough", "url": "https://a", "score": 100, "by": "u", "time": 1},
        2: {"id": 2, "title": "Low score", "url": "https://b", "score": 10, "by": "u", "time": 2},
        3: {"id": 3, "title": "Borderline", "url": "https://c", "score": 50, "by": "u", "time": 3},
    }

    async def fake_fetch(top_limit=200):
        return [items[i] for i in (1, 2, 3)]

    monkeypatch.setattr(hn, "_fetch_top_async", fake_fetch)

    result = hn.fetch_hn_top_stories()

    ids = sorted(article["id"] for article in result)
    assert ids == [1, 3]
    # ordering by score desc
    assert result[0]["id"] == 1
    assert all(article["source"] == "hn" for article in result)


def test_fetch_hn_top_stories_handles_missing_url(monkeypatch):
    from fetchers import hn

    async def fake_fetch(top_limit=200):
        return [{"id": 42, "title": "ASK HN", "score": 80, "by": "u", "time": 1}]

    monkeypatch.setattr(hn, "_fetch_top_async", fake_fetch)

    result = hn.fetch_hn_top_stories()

    assert result[0]["url"] == "https://news.ycombinator.com/item?id=42"


def test_fetch_hn_top_stories_handles_empty(monkeypatch):
    from fetchers import hn

    async def fake_fetch(top_limit=200):
        return []

    monkeypatch.setattr(hn, "_fetch_top_async", fake_fetch)

    assert hn.fetch_hn_top_stories() == []


def test_fetch_hn_top_stories_rejects_dangerous_url(monkeypatch):
    """A ``javascript:`` URL must be replaced with the canonical HN item page."""
    from fetchers import hn

    async def fake_fetch(top_limit=200):
        return [
            {
                "id": 99,
                "title": "Hostile",
                "url": "javascript:alert(1)",
                "score": 80,
                "by": "u",
                "time": 1,
            },
        ]

    monkeypatch.setattr(hn, "_fetch_top_async", fake_fetch)

    result = hn.fetch_hn_top_stories()

    assert result[0]["url"] == "https://news.ycombinator.com/item?id=99"


def test_fetch_hn_top_stories_handles_timeout(monkeypatch):
    """A per-item ``httpx.TimeoutException`` must be swallowed (item dropped)."""
    import httpx

    from fetchers import hn

    class _FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            if url == hn.TOP_STORIES_URL:
                resp = MagicMock()
                resp.json.return_value = [123]
                resp.raise_for_status.return_value = None
                return resp
            raise httpx.TimeoutException("boom")

    monkeypatch.setattr(hn.httpx, "AsyncClient", _FakeAsyncClient)

    # Should not raise, and the timed-out item is silently dropped.
    assert hn.fetch_hn_top_stories() == []


# ---------------------------------------------------------------------------
# fetchers/hf_papers.py
# ---------------------------------------------------------------------------


def test_fetch_hf_papers_normalizes_payload():
    from fetchers import hf_papers

    sample = [
        {
            "title": "Attention Is All You Need (Again)",
            "paper": {
                "id": "2401.00001",
                "upvotes": 42,
                "publishedAt": "2026-04-29T00:00:00Z",
                "summary": "A paper about transformers.",
            },
        },
        {
            "title": "Defensive — missing paper id",
            "paper": {"upvotes": 5},
        },
        {"title": "Defensive — no paper key"},
        "garbage row",
    ]

    fake_response = MagicMock()
    fake_response.json.return_value = sample
    fake_response.raise_for_status.return_value = None

    fake_client = MagicMock()
    fake_client.get.return_value = fake_response
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)

    with patch("fetchers.hf_papers.httpx.Client", return_value=fake_client):
        result = hf_papers.fetch_hf_papers()

    assert len(result) == 1
    article = result[0]
    assert article["url"] == "https://huggingface.co/papers/2401.00001"
    assert article["score"] == 42
    assert article["source"] == "hf_papers"
    assert article["title"].startswith("Attention")


def test_fetch_hf_papers_empty_response():
    from fetchers import hf_papers

    fake_response = MagicMock()
    fake_response.json.return_value = []
    fake_response.raise_for_status.return_value = None

    fake_client = MagicMock()
    fake_client.get.return_value = fake_response
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)

    with patch("fetchers.hf_papers.httpx.Client", return_value=fake_client):
        result = hf_papers.fetch_hf_papers()

    assert result == []


def test_fetch_hf_papers_timeout_returns_empty():
    import httpx

    from fetchers import hf_papers

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get.side_effect = httpx.TimeoutException("timeout")

    with patch("fetchers.hf_papers.httpx.Client", return_value=fake_client):
        result = hf_papers.fetch_hf_papers()

    assert result == []


def test_fetch_hf_papers_skips_corrupt_url(monkeypatch):
    """Defense in depth: if URL construction yields something non-http, drop the row."""
    from fetchers import hf_papers

    sample = [
        {
            "title": "Will be skipped",
            "paper": {"id": "anything", "upvotes": 10},
        },
    ]

    fake_response = MagicMock()
    fake_response.json.return_value = sample
    fake_response.raise_for_status.return_value = None

    fake_client = MagicMock()
    fake_client.get.return_value = fake_response
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)

    # Force the URL template to a hostile scheme so ``is_safe_url`` rejects it.
    monkeypatch.setattr(
        hf_papers,
        "PAPER_URL_TEMPLATE",
        "javascript:alert('{arxiv_id}')",
    )

    with patch("fetchers.hf_papers.httpx.Client", return_value=fake_client):
        result = hf_papers.fetch_hf_papers()

    assert result == []


# ---------------------------------------------------------------------------
# fetchers/rss.py
# ---------------------------------------------------------------------------


def test_fetch_hn_rss_parses_entries():
    from fetchers import rss

    entry1 = MagicMock()
    entry1.title = "AI agents take over"
    entry1.link = "https://example.com/article"
    entry1.published = "Tue, 29 Apr 2026 00:00:00 GMT"

    entry2 = MagicMock()
    entry2.title = "Bad scheme"
    entry2.link = "ftp://nope"
    entry2.published = "Tue, 29 Apr 2026 00:00:00 GMT"

    feed = MagicMock()
    feed.entries = [entry1, entry2]

    with patch("fetchers.rss.feedparser.parse", return_value=feed):
        result = rss.fetch_hn_rss()

    assert len(result) == 1
    assert result[0]["title"] == "AI agents take over"
    assert result[0]["url"].startswith("https://")
    assert result[0]["source"] == "rss"


def test_fetch_hn_rss_empty_feed():
    from fetchers import rss

    feed = MagicMock()
    feed.entries = []

    with patch("fetchers.rss.feedparser.parse", return_value=feed):
        result = rss.fetch_hn_rss()

    assert result == []


# ---------------------------------------------------------------------------
# fetchers package: fetch_all + cache integration
# ---------------------------------------------------------------------------


def test_fetch_all_caches_then_serves(tmp_cache_db, monkeypatch):
    import fetchers

    calls = {"hn": 0, "hf": 0, "rss": 0}

    def fake_hn(top_limit=200):
        calls["hn"] += 1
        return [{"id": 1, "title": "AI thing", "url": "https://a", "score": 99, "source": "hn"}]

    def fake_hf(target_date=None, limit=30):
        calls["hf"] += 1
        return [{"title": "Paper", "url": "https://huggingface.co/papers/x", "score": 5, "source": "hf_papers"}]

    def fake_rss(url=None):
        calls["rss"] += 1
        return [{"title": "RSS", "url": "https://b", "source": "rss"}]

    monkeypatch.setattr(fetchers, "fetch_hn_top_stories", fake_hn)
    monkeypatch.setattr(fetchers, "fetch_hf_papers", fake_hf)
    monkeypatch.setattr(fetchers, "fetch_hn_rss", fake_rss)

    first = fetchers.fetch_all()
    assert calls == {"hn": 1, "hf": 1, "rss": 1}
    assert set(first.keys()) == {"hn", "hf_papers", "rss"}

    second = fetchers.fetch_all()
    # Cache hit: counters do not advance.
    assert calls == {"hn": 1, "hf": 1, "rss": 1}
    assert second == first


def test_fetch_all_force_refresh_bypasses_cache(tmp_cache_db, monkeypatch):
    import fetchers

    counter = {"n": 0}

    def fake_hn(top_limit=200):
        counter["n"] += 1
        return [{"id": counter["n"], "title": f"v{counter['n']}", "url": "https://a", "score": 99, "source": "hn"}]

    monkeypatch.setattr(fetchers, "fetch_hn_top_stories", fake_hn)
    monkeypatch.setattr(fetchers, "fetch_hf_papers", lambda *a, **k: [])
    monkeypatch.setattr(fetchers, "fetch_hn_rss", lambda *a, **k: [])

    fetchers.fetch_all()
    fetchers.fetch_all(force_refresh=True)

    assert counter["n"] == 2


# ---------------------------------------------------------------------------
# ui/filters.py
# ---------------------------------------------------------------------------


def test_is_ai_related_positive():
    from ui.filters import is_ai_related

    assert is_ai_related({"title": "ChatGPT API Guide"}) is True
    assert is_ai_related({"title": "Diffusion model release"}) is True
    assert is_ai_related({"title": "Plain title", "summary": "Uses LLM in production"}) is True


def test_is_ai_related_negative():
    from ui.filters import is_ai_related

    assert is_ai_related({"title": "How to Cook Pasta"}) is False
    assert is_ai_related({"title": "", "summary": ""}) is False


def test_filter_articles_keeps_only_ai():
    from ui.filters import filter_articles

    articles = [
        {"title": "ChatGPT release"},
        {"title": "Banana bread recipe"},
        {"title": "GPT-5 leak"},
    ]
    result = filter_articles(articles)

    assert len(result) == 2
    assert all("title" in a for a in result)


# ---------------------------------------------------------------------------
# Integration: fetchers + ui/render with no-op translator
# (タイトル翻訳経由でも既存パイプラインが壊れないことの確認)
# ---------------------------------------------------------------------------


def test_fetch_all_pipeline_works_with_noop_translator(tmp_cache_db, monkeypatch):
    """``translate_title`` を no-op にしても ``fetch_all`` の出力が従来通りであること。"""
    import fetchers

    # 翻訳を no-op (原題そのまま返す) に差し替える。fetchers は翻訳を呼ばないが、
    # 「翻訳統合後も既存フェッチパスが壊れない」ことを明示的に確かめる。
    import translator

    monkeypatch.setattr(translator, "translate_title", lambda title: title)

    monkeypatch.setattr(
        fetchers,
        "fetch_hn_top_stories",
        lambda **_: [
            {"id": 1, "title": "AI breakthrough", "url": "https://a", "score": 99, "source": "hn"}
        ],
    )
    monkeypatch.setattr(
        fetchers,
        "fetch_hf_papers",
        lambda **_: [
            {"title": "Paper", "url": "https://huggingface.co/papers/x", "score": 5, "source": "hf_papers"}
        ],
    )
    monkeypatch.setattr(
        fetchers,
        "fetch_hn_rss",
        lambda **_: [{"title": "RSS Item", "url": "https://b", "source": "rss"}],
    )

    result = fetchers.fetch_all()

    assert set(result.keys()) == {"hn", "hf_papers", "rss"}
    assert result["hn"][0]["title"] == "AI breakthrough"
    assert result["hf_papers"][0]["title"] == "Paper"
    assert result["rss"][0]["title"] == "RSS Item"


def test_render_card_invokes_translator_with_title(tmp_cache_db, monkeypatch):
    """render_article_card が translate_title を経由してタイトルを取得すること。"""
    captured = {}

    def fake_translate(title):
        captured["called_with"] = title
        # サニタイザは [, ], (, ) を除去するため、ここでは含めない。
        return f"日本語訳: {title}"

    # render は ``from translator import translate_title`` で関数を取り込むため、
    # ``ui.render`` モジュール側のシンボルを差し替える必要がある。
    from ui import render as render_module

    monkeypatch.setattr(render_module, "translate_title", fake_translate)

    # Streamlit 側の副作用 (markdown/caption/write/divider) はすべてモック化。
    fake_st = MagicMock()
    monkeypatch.setattr(render_module, "st", fake_st)

    article = {
        "title": "Hello AI",
        "url": "https://example.com",
        "score": 42,
        "source": "hn",
        "by": "alice",
    }

    render_module.render_article_card(article)

    assert captured["called_with"] == "Hello AI"
    # 翻訳結果が markdown 出力に含まれていること。
    md_calls = [c.args[0] for c in fake_st.markdown.call_args_list]
    assert any("日本語訳: Hello AI" in s for s in md_calls)
    # 原題併記の caption が呼ばれていること(翻訳が原題と異なるため)。
    caption_calls = [c.args[0] for c in fake_st.caption.call_args_list]
    assert any("原題: Hello AI" in s for s in caption_calls)
