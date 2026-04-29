"""HN RSS feed fetcher (filtered for AI keyword, points >= 50)."""

from __future__ import annotations

from typing import Any

import feedparser

from ui.safety import is_safe_url

RSS_URL = "https://hnrss.org/newest?q=AI&points=50&count=50"


def _entry_field(entry: Any, key: str) -> Any:
    """Pull ``key`` off a feedparser entry, supporting both attr and mapping access."""
    value = getattr(entry, key, None)
    if value is not None:
        return value
    if isinstance(entry, dict):
        return entry.get(key)
    return None


def fetch_hn_rss(url: str = RSS_URL) -> list[dict[str, Any]]:
    """Parse the HN RSS feed and return normalized entries.

    Returns
    -------
    list[dict]
        Each dict has ``title``, ``url``, ``source`` (= ``"rss"``), and the
        raw ``published`` string when provided by the feed.
    """
    feed = feedparser.parse(url)

    entries = getattr(feed, "entries", None) or []
    results: list[dict[str, Any]] = []
    for entry in entries:
        title = _entry_field(entry, "title")
        link = _entry_field(entry, "link")
        published = _entry_field(entry, "published")

        if not title or not link:
            continue
        if not is_safe_url(link):
            continue

        results.append(
            {
                "title": title,
                "url": link,
                "published": published,
                "source": "rss",
            }
        )

    return results


__all__ = ["fetch_hn_rss", "RSS_URL"]
