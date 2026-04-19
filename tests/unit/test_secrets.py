"""Unit tests for ``playwright_god._secrets``."""

from __future__ import annotations

import re

from playwright_god import _secrets


def test_redact_authorization_bearer_header():
    out = _secrets.redact("Authorization: Bearer sk-abcdef0123456789ABC")
    assert "sk-abcdef0123456789ABC" not in out
    assert "[REDACTED]" in out


def test_redact_naked_bearer_token():
    out = _secrets.redact("see also: Bearer abcdef0123456789ABCDEF")
    assert "abcdef0123456789ABCDEF" not in out


def test_redact_openai_provider_key():
    leak = "log line: sk-proj-XYZabc1234567890DEFGHIJK"
    out = _secrets.redact(leak)
    assert "sk-proj-XYZabc1234567890DEFGHIJK" not in out
    assert "[REDACTED]" in out


def test_redact_anthropic_key():
    leak = "ANTHROPIC: sk-ant-abcdef0123456789xyz"
    out = _secrets.redact(leak)
    assert "sk-ant-abcdef0123456789xyz" not in out


def test_redact_github_pat():
    out = _secrets.redact("token: ghp_abcdef0123456789abcdef0123456789ABCD")
    assert "ghp_abcdef" not in out


def test_redact_google_api_key():
    out = _secrets.redact("key=AIzaSyAbcdEFghIJ0123456789xyz_-")
    assert "AIzaSy" not in out


def test_redact_env_var_assignment_for_known_secret_name():
    out = _secrets.redact("OPENAI_API_KEY=sk-real-secret-abcdef0123")
    assert "sk-real-secret-abcdef0123" not in out
    assert "[REDACTED]" in out


def test_redact_password_assignment_in_plaintext():
    out = _secrets.redact("password=hunter2hunter2")
    assert "hunter2hunter2" not in out


def test_redact_idempotent():
    once = _secrets.redact("Authorization: Bearer sk-abcdef0123456789ABC")
    twice = _secrets.redact(once)
    assert once == twice


def test_redact_empty_returns_empty():
    assert _secrets.redact("") == ""


def test_redact_none_safe_input_unchanged():
    out = _secrets.redact("nothing secret here")
    assert out == "nothing secret here"


def test_make_code_replacer_calls_callback_only_when_substituting():
    calls = []
    pattern, replacement = _secrets._SECRET_PATTERNS[0]  # password
    cb = _secrets.make_code_replacer(replacement, on_replace=lambda: calls.append(1))
    result = pattern.sub(cb, 'password = "supersecret"')
    assert "supersecret" not in result
    assert calls == [1]


def test_make_code_replacer_skips_safe_values():
    calls = []
    pattern, replacement = _secrets._SECRET_PATTERNS[0]
    cb = _secrets.make_code_replacer(replacement, on_replace=lambda: calls.append(1))
    safe = 'password = "process.env.TEST_PASSWORD"'
    result = pattern.sub(cb, safe)
    assert calls == []
    # Original safe placeholder unchanged.
    assert "process.env.TEST_PASSWORD" in result


def test_make_code_replacer_callback_optional():
    pattern, replacement = _secrets._SECRET_PATTERNS[0]
    cb = _secrets.make_code_replacer(replacement)
    result = pattern.sub(cb, 'password = "leaked99"')
    assert "leaked99" not in result
