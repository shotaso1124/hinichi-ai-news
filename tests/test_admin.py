"""Tests for the admin gate (URL ?admin=token vs Streamlit Secrets)."""

from __future__ import annotations

from app import _check_admin


def test_check_admin_returns_false_when_expected_is_empty() -> None:
    """When secrets is unset, no token can pass."""
    assert _check_admin("anything", "") is False


def test_check_admin_returns_false_when_token_is_empty() -> None:
    """A missing URL param must never grant admin access."""
    assert _check_admin("", "expected") is False


def test_check_admin_returns_false_when_both_empty() -> None:
    """Both empty -> read-only mode."""
    assert _check_admin("", "") is False


def test_check_admin_returns_false_when_tokens_mismatch() -> None:
    """Wrong token -> read-only mode."""
    assert _check_admin("wrong_token", "expected_token") is False


def test_check_admin_returns_true_when_tokens_match() -> None:
    """Matching token -> admin mode."""
    assert _check_admin("correct_token", "correct_token") is True


def test_check_admin_is_case_sensitive() -> None:
    """Tokens are compared exactly; case differences must fail."""
    assert _check_admin("Token", "token") is False


def test_check_admin_with_real_world_length_token() -> None:
    """32-char alphanumeric tokens are the recommended format."""
    token = "5fxQDS5t0MEEryCFZFPpKvELXW8EEte7"
    assert _check_admin(token, token) is True
    assert _check_admin(token + "x", token) is False
