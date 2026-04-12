"""Unit tests for playwright_god.auth_templates."""

from __future__ import annotations

from playwright_god.auth_templates import AUTH_TYPES, get_auth_hint, get_template


def test_get_template_returns_expected_python_snippets():
    saml = get_template("saml")
    ntlm = get_template("ntlm")
    oidc = get_template("oidc")
    logging = get_template("logging")

    assert saml is not None and "sign_in_with_saml" in saml
    assert ntlm is not None and "http_credentials" in ntlm
    assert oidc is not None and "sign_in_with_oidc" in oidc
    assert logging is not None and "capture_route" in logging


def test_get_template_is_case_insensitive_and_handles_missing_values():
    assert get_template("SAML") == get_template("saml")
    assert get_template("basic") is None
    assert get_template("unknown") is None


def test_get_auth_hint_returns_expected_values():
    assert "SAML" in (get_auth_hint("saml") or "")
    assert "NTLM" in (get_auth_hint("ntlm") or "")
    assert "OIDC" in (get_auth_hint("oidc") or "")
    assert "Basic" in (get_auth_hint("basic") or "")
    assert "console" in (get_auth_hint("logging") or "")


def test_get_auth_hint_is_case_insensitive_and_handles_none():
    assert get_auth_hint("SAML") == get_auth_hint("saml")
    assert get_auth_hint("none") is None
    assert "none" in AUTH_TYPES
