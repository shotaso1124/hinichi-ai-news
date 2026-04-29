"""AI keyword filter for fetched articles."""

from __future__ import annotations

from typing import Iterable

AI_KEYWORDS: set[str] = {
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "neural network", "llm", "large language model", "gpt", "claude",
    "gemini", "transformer", "diffusion", "reinforcement learning",
    "computer vision", "nlp", "natural language", "generative",
    "foundation model", "fine-tuning", "rag", "agent", "multimodal",
    "openai", "anthropic", "hugging face", "pytorch", "tensorflow",
}


def _haystack(article: dict) -> str:
    parts = [
        str(article.get("title") or ""),
        str(article.get("summary") or ""),
    ]
    return " ".join(parts).lower()


def is_ai_related(article: dict) -> bool:
    """Return True when the article's title/summary contains an AI keyword."""
    haystack = _haystack(article)
    if not haystack.strip():
        return False
    return any(keyword in haystack for keyword in AI_KEYWORDS)


def filter_articles(articles: Iterable[dict]) -> list[dict]:
    """Return only articles whose title/summary mentions any AI keyword."""
    return [article for article in articles if is_ai_related(article)]


__all__ = ["AI_KEYWORDS", "is_ai_related", "filter_articles"]
