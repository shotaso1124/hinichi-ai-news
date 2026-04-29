"""URL/Markdown safety helpers shared across UI and fetchers.

The Streamlit cards render external API content as Markdown links. Without
validation, hostile input such as ``javascript:alert(1)`` URLs or
``](javascript:...)`` injections inside titles could trigger XSS / clickjack
attacks. The helpers here are the single source of truth for sanitization.
"""

from __future__ import annotations

_SAFE_SCHEMES: tuple[str, ...] = ("http://", "https://")


def is_safe_url(url: object) -> bool:
    """Return ``True`` only when ``url`` is an ``http://`` or ``https://`` string.

    Anything else (``None``, empty string, ``javascript:``, ``data:``, ``file:``,
    relative paths, non-string types) is rejected. This is intentionally a
    strict allowlist — we never need any other scheme in this app.
    """
    if not isinstance(url, str):
        return False
    return url.lower().startswith(_SAFE_SCHEMES)


def sanitize_markdown_text(text: object) -> str:
    """Strip Markdown link/image syntax characters from arbitrary text.

    External titles are rendered inside ``[ ... ]( ... )`` link constructs.
    Removing brackets/parens prevents an attacker from breaking out of the
    label and injecting their own URL (e.g. ``Foo](javascript:alert(1))``).
    """
    if text is None:
        return ""
    return (
        str(text)
        .replace("[", "")
        .replace("]", "")
        .replace("(", "")
        .replace(")", "")
    )


__all__ = ["is_safe_url", "sanitize_markdown_text"]
