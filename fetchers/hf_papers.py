"""HuggingFace Daily Papers fetcher."""

from __future__ import annotations

from datetime import date as date_cls
from typing import Any

import httpx

from ui.safety import is_safe_url

DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
PAPER_URL_TEMPLATE = "https://huggingface.co/papers/{arxiv_id}"
DEFAULT_LIMIT = 30
REQUEST_TIMEOUT = 15.0


def fetch_hf_papers(
    target_date: date_cls | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Fetch HuggingFace Daily Papers for a given date.

    Parameters
    ----------
    target_date:
        Defaults to today (UTC).
    limit:
        Number of papers to request.

    Returns
    -------
    list[dict]
        Each dict has at least ``title``, ``url``, ``score``, ``source``, plus
        ``summary`` and ``published_at`` when present.
    """
    target = target_date or date_cls.today()
    params = {"date": target.isoformat(), "limit": limit}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(DAILY_PAPERS_URL, params=params)
            resp.raise_for_status()
            articles = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    if not isinstance(articles, list):
        return []

    results: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        paper = article.get("paper", {}) or {}
        arxiv_id = paper.get("id")
        if not arxiv_id:
            continue
        title = article.get("title") or paper.get("title")
        if not title:
            continue
        url = PAPER_URL_TEMPLATE.format(arxiv_id=arxiv_id)
        # Defense in depth: ``arxiv_id`` is interpolated into a fixed
        # ``https://`` template, but we still validate the result before
        # surfacing it, in case the upstream payload includes a bogus id.
        if not is_safe_url(url):
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "score": paper.get("upvotes", 0) or 0,
                "summary": paper.get("summary", ""),
                "published_at": paper.get("publishedAt"),
                "source": "hf_papers",
            }
        )

    results.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return results


__all__ = ["fetch_hf_papers", "DAILY_PAPERS_URL", "PAPER_URL_TEMPLATE"]
