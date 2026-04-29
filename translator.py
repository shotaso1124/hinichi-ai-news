"""タイトル翻訳モジュール — Claude Haiku で英語タイトルを日本語訳。

英語ニュースタイトルを Anthropic Claude Haiku で日本語に翻訳し、
SQLite キャッシュ (``store/news_cache.db`` 内 ``translations`` テーブル) に永続保存する。

設計方針
---------
- API キー未設定 / API エラー / 異常な翻訳結果のすべてで原題そのままにフォールバック。
  → アプリは API キーなしでも壊れず動作する。
- キャッシュは原題をプライマリキーとする。同じタイトルが複数フィードにまたがって
  出現しても 1 度しか API を叩かない。
- 文字列以外・空文字列はそのまま返す（API を叩かない）。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

# ``store/cache.py`` と同じ DB を共有する。``AI_NEWS_CACHE_DB`` で上書き可能。
_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "store" / "news_cache.db"


def _db_path() -> Path:
    override = os.environ.get("AI_NEWS_CACHE_DB")
    if override:
        return Path(override)
    return _DEFAULT_DB_PATH


def _ensure_translation_table() -> None:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                original_title TEXT PRIMARY KEY,
                translated_title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def get_cached_translation(original_title: str) -> Optional[str]:
    """キャッシュ済み翻訳を返す。なければ ``None``。"""
    if not isinstance(original_title, str) or not original_title:
        return None
    _ensure_translation_table()
    with closing(sqlite3.connect(_db_path())) as conn:
        row = conn.execute(
            "SELECT translated_title FROM translations WHERE original_title = ?",
            (original_title,),
        ).fetchone()
        return row[0] if row else None


def cache_translation(original_title: str, translated_title: str) -> None:
    """翻訳結果を永続キャッシュに保存(UPSERT)。"""
    if not isinstance(original_title, str) or not isinstance(translated_title, str):
        return
    if not original_title or not translated_title:
        return
    _ensure_translation_table()
    with closing(sqlite3.connect(_db_path())) as conn:
        conn.execute(
            """
            INSERT INTO translations (original_title, translated_title, created_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(original_title) DO UPDATE SET
                translated_title = excluded.translated_title,
                created_at = excluded.created_at
            """,
            (original_title, translated_title),
        )
        conn.commit()


def _is_api_key_valid(api_key: str) -> bool:
    """プレースホルダや明らかに無効なキーを除外する軽い前段チェック。"""
    if not api_key:
        return False
    # ``.env.example`` 等のダミー値は弾く。
    if api_key.startswith("sk-ant-XXX"):
        return False
    return True


def translate_title(original_title: str) -> str:
    """英語タイトルを日本語訳して返す。

    - API キー未設定 / 失敗 / 異常レスポンス時は原題をそのまま返す。
    - 一度訳した結果は SQLite に永続キャッシュする。
    """
    if not isinstance(original_title, str) or not original_title.strip():
        return original_title if isinstance(original_title, str) else ""

    cached = get_cached_translation(original_title)
    if cached:
        return cached

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _is_api_key_valid(api_key):
        return original_title

    try:
        # ``anthropic`` は実 API 利用時のみ必要。未インストールでもアプリ自体は動く。
        from anthropic import Anthropic  # type: ignore[import-not-found]

        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "次の英語ニュースタイトルを自然な日本語に翻訳してください。"
                        "翻訳結果のみを返してください(前置きや説明は不要)。\n\n"
                        f"タイトル: {original_title}"
                    ),
                }
            ],
        )

        # SDK のレスポンス形 (content[0].text) に依存するが、想定外の形でも
        # 例外を握りつぶしてフォールバックするので安全。
        translated = ""
        if msg and getattr(msg, "content", None):
            block = msg.content[0]
            translated = getattr(block, "text", "") or ""
        translated = translated.strip()

        # サニティチェック: 空・原題と同じ・極端に長い場合はフォールバック。
        if not translated or translated == original_title or len(translated) > 200:
            return original_title

        cache_translation(original_title, translated)
        return translated
    except Exception:  # noqa: BLE001 — どのような例外でもフォールバック
        return original_title


__all__ = [
    "translate_title",
    "get_cached_translation",
    "cache_translation",
]
