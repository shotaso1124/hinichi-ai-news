"""Hacker News top-stories fetcher.

Hits the public Firebase API, fans out the top 200 IDs through an
``httpx.AsyncClient`` (concurrency 25), filters by ``score >= 50``, and
returns a normalized list of dicts.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ui.safety import is_safe_url

TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={item_id}"

TOP_LIMIT = 200
MIN_SCORE = 50
CONCURRENCY = 25
REQUEST_TIMEOUT = 10.0


async def _fetch_item(
    client: httpx.AsyncClient,
    item_id: int,
    sem: asyncio.Semaphore,
) -> dict[str, Any] | None:
    async with sem:
        try:
            resp = await client.get(ITEM_URL.format(item_id=item_id))
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError):
            # ``TimeoutException`` is a subclass of ``HTTPError`` in httpx 0.27,
            # but listing it explicitly guards against future refactors and
            # makes the intent obvious.
            return None


async def _fetch_top_async(top_limit: int = TOP_LIMIT) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(TOP_STORIES_URL)
        resp.raise_for_status()
        ids: list[int] = resp.json()[:top_limit]

        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = [_fetch_item(client, item_id, sem) for item_id in ids]
        items = await asyncio.gather(*tasks)

    return [item for item in items if item]


def fetch_hn_top_stories(top_limit: int = TOP_LIMIT) -> list[dict[str, Any]]:
    """Fetch HN top stories with ``score >= 50``.

    Returns
    -------
    list[dict]
        Each dict contains the keys ``id``, ``title``, ``url``, ``score``,
        ``by``, ``time``, plus a ``source`` marker (``"hn"``).
    """
    items = asyncio.run(_fetch_top_async(top_limit=top_limit))

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        score = item.get("score") or 0
        if score < MIN_SCORE:
            continue
        title = item.get("title")
        if not title:
            continue
        item_id = item.get("id")
        # Validate the external URL — HN occasionally has Ask/Show items where
        # ``url`` is missing or malformed. Anything that isn't ``http(s)://``
        # falls back to the canonical HN item page (always safe).
        candidate_url = item.get("url")
        if is_safe_url(candidate_url):
            url = candidate_url
        else:
            url = HN_ITEM_PAGE.format(item_id=item_id)
        results.append(
            {
                "id": item_id,
                "title": title,
                "url": url,
                "score": score,
                "by": item.get("by"),
                "time": item.get("time"),
                "source": "hn",
            }
        )

    results.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return results


__all__ = ["fetch_hn_top_stories", "TOP_LIMIT", "MIN_SCORE"]
