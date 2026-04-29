"""Fetcher orchestration with TTL caching.

Provides ``fetch_all()`` which queries each source (HN top stories, HF Daily
Papers, HN RSS), routing through the SQLite TTL cache in ``store/cache.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from store.cache import get as cache_get
from store.cache import set as cache_set

from .hf_papers import fetch_hf_papers
from .hn import fetch_hn_top_stories
from .rss import fetch_hn_rss

CACHE_TTL_MINUTES = 30


def fetch_all(force_refresh: bool = False) -> dict[str, list[dict]]:
    """Fetch all three sources, using cache when available.

    Parameters
    ----------
    force_refresh:
        If True, bypass the cache and fetch fresh data from each source.

    Returns
    -------
    dict[str, list[dict]]
        Keys: ``"hn"``, ``"hf_papers"``, ``"rss"``.
    """
    today_key = date.today().isoformat()

    sources: dict[str, tuple[str, Callable[..., list[dict[str, Any]]]]] = {
        "hn": ("topstories", fetch_hn_top_stories),
        "hf_papers": (today_key, fetch_hf_papers),
        "rss": ("newest_ai", fetch_hn_rss),
    }

    result: dict[str, list[dict]] = {}
    for source_name, (cache_key, fetcher) in sources.items():
        if not force_refresh:
            cached = cache_get(source_name, cache_key)
            if cached is not None:
                result[source_name] = cached
                continue
        data = fetcher()
        cache_set(source_name, cache_key, data, ttl_minutes=CACHE_TTL_MINUTES)
        result[source_name] = data

    return result


__all__ = ["fetch_all", "CACHE_TTL_MINUTES"]
