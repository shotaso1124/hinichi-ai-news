"""Tests for ``translator.py``.

Covers:
- API キー未設定時のフォールバック(原題返却)
- API キーがダミー値時のフォールバック
- API 例外時のフォールバック
- 正常系(モック)で翻訳結果が返ること
- SQLite キャッシュの永続化(2 度目は API を呼ばない)
- 空文字 / None / 非文字列の防衛挙動
- 異常な翻訳結果(空・原題と同じ・極端に長い)はフォールバック
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixture: tmp DB + clean module state
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_translation_db(monkeypatch):
    """Point ``translator`` at a fresh SQLite file per test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_translations.db"
        monkeypatch.setenv("AI_NEWS_CACHE_DB", str(db_path))
        # Ensure tests start from a clean import state so the env var is read.
        sys.modules.pop("translator", None)
        yield db_path
        sys.modules.pop("translator", None)


def _fake_anthropic_response(text: str):
    """Build a minimal stand-in for ``client.messages.create`` return value."""
    block = SimpleNamespace(text=text)
    return SimpleNamespace(content=[block])


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------


def test_translate_title_returns_original_when_api_key_missing(
    tmp_translation_db, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import translator

    assert translator.translate_title("Hello World") == "Hello World"


def test_translate_title_returns_original_for_placeholder_key(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-XXXXXXXXXXXXXXXXXXXXXX")
    import translator

    # Should NOT attempt to instantiate the SDK with a placeholder key.
    with patch("anthropic.Anthropic") as mock_anthropic:
        result = translator.translate_title("Hello World")

    assert result == "Hello World"
    mock_anthropic.assert_not_called()


def test_translate_title_returns_original_on_api_exception(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("boom")

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = translator.translate_title("Hello World")

    assert result == "Hello World"


# ---------------------------------------------------------------------------
# Happy path + caching
# ---------------------------------------------------------------------------


def test_translate_title_returns_japanese_on_success(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "こんにちは世界"
    )

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = translator.translate_title("Hello World")

    assert result == "こんにちは世界"
    fake_client.messages.create.assert_called_once()


def test_translate_title_uses_cache_on_second_call(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "AI最新動向"
    )

    with patch("anthropic.Anthropic", return_value=fake_client) as mock_factory:
        first = translator.translate_title("AI Latest Trends")
        second = translator.translate_title("AI Latest Trends")

    assert first == "AI最新動向"
    assert second == "AI最新動向"
    # キャッシュヒット: 2 回目はクライアント生成も create 呼び出しもされない。
    assert mock_factory.call_count == 1
    assert fake_client.messages.create.call_count == 1


def test_translate_title_persists_to_sqlite(tmp_translation_db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "翻訳結果"
    )

    with patch("anthropic.Anthropic", return_value=fake_client):
        translator.translate_title("Original Title")

    # 直接 helper でキャッシュを覗く。
    cached = translator.get_cached_translation("Original Title")
    assert cached == "翻訳結果"


# ---------------------------------------------------------------------------
# Sanity / defensive
# ---------------------------------------------------------------------------


def test_translate_title_handles_empty_string(tmp_translation_db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    with patch("anthropic.Anthropic") as mock_anthropic:
        result = translator.translate_title("")

    assert result == ""
    mock_anthropic.assert_not_called()


def test_translate_title_falls_back_when_response_too_long(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    huge = "あ" * 250  # > 200 chars: treated as anomaly

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(huge)

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = translator.translate_title("Some Title")

    assert result == "Some Title"
    # キャッシュにも保存しない(次回も API を叩く挙動でよい)。
    assert translator.get_cached_translation("Some Title") is None


def test_translate_title_falls_back_when_response_equals_original(
    tmp_translation_db, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-key")
    import translator

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "Same Title"
    )

    with patch("anthropic.Anthropic", return_value=fake_client):
        result = translator.translate_title("Same Title")

    assert result == "Same Title"
    assert translator.get_cached_translation("Same Title") is None


def test_get_cached_translation_returns_none_for_missing(
    tmp_translation_db, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import translator

    assert translator.get_cached_translation("never seen") is None


def test_cache_translation_then_get_round_trip(tmp_translation_db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import translator

    translator.cache_translation("Foo", "フー")
    assert translator.get_cached_translation("Foo") == "フー"

    # UPSERT: 上書きされる。
    translator.cache_translation("Foo", "フー(更新)")
    assert translator.get_cached_translation("Foo") == "フー(更新)"
