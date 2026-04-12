"""Auth fixture templates for Python Playwright tests."""

from __future__ import annotations

SAML_AUTH_TEMPLATE: str = """\
import os

from playwright.sync_api import Page, expect


def sign_in_with_saml(page: Page) -> None:
    page.goto(os.environ.get("SP_LOGIN_URL", "https://app.example.com/saml/login"))
    page.get_by_label("Username").fill(os.environ.get("TEST_USERNAME", ""))
    page.get_by_label("Password").fill(os.environ.get("TEST_PASSWORD", ""))
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("https://app.example.com/home")
    expect(page).to_have_url("https://app.example.com/home")
"""

NTLM_AUTH_TEMPLATE: str = """\
import os

from playwright.sync_api import Browser, BrowserContext, expect


def authenticated_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        http_credentials={
            "username": os.environ.get("TEST_USERNAME", ""),
            "password": os.environ.get("TEST_PASSWORD", ""),
        }
    )
"""

OIDC_AUTH_TEMPLATE: str = """\
import os

from playwright.sync_api import Page, expect


def sign_in_with_oidc(page: Page) -> None:
    page.goto(os.environ.get("APP_LOGIN_URL", "https://app.example.com/auth/login"))
    page.get_by_label("Email").fill(os.environ.get("TEST_USERNAME", ""))
    page.get_by_label("Password").fill(os.environ.get("TEST_PASSWORD", ""))
    page.get_by_role("button", name="Continue").click()
    page.wait_for_url("https://app.example.com/home")
    expect(page).to_have_url("https://app.example.com/home")
"""

LOGGING_FIXTURE_TEMPLATE: str = """\
from playwright.sync_api import Page


def attach_log_listeners(
    page: Page,
    messages: list[str],
    errors: list[str],
    audit_requests: list[str],
) -> None:
    def capture_route(route) -> None:
        audit_requests.append(route.request.url)
        route.continue_()

    page.on("console", lambda msg: messages.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: errors.append(err.message))
    page.route("**/*", capture_route)
"""

_AUTH_HINTS: dict[str, str] = {
    "saml": (
        "Auth type: SAML SSO.\n"
        "- Use helper functions or fixtures that navigate through the IdP and assert the post-login landing page.\n"
        "- Reference credentials through os.environ values such as TEST_USERNAME and TEST_PASSWORD.\n"
        "- Use page.wait_for_url() for redirect-heavy sign-in flows.\n"
        "- Preserve authenticated state for later tests when the workflow is expensive."
    ),
    "ntlm": (
        "Auth type: NTLM or Kerberos.\n"
        "- Use browser.new_context(http_credentials=...) in Python Playwright.\n"
        "- Reference credentials through os.environ values.\n"
        "- Assert the page loads without redirecting back to login."
    ),
    "oidc": (
        "Auth type: OIDC authorization-code flow.\n"
        "- Model the provider redirect and callback in Python Playwright fixtures.\n"
        "- Reference credentials through os.environ values.\n"
        "- Keep MFA or consent steps explicit when the repository signals they are required."
    ),
    "basic": (
        "Auth type: HTTP Basic Authentication.\n"
        "- Use browser.new_context(http_credentials=...) and avoid hard-coded secrets."
    ),
    "logging": (
        "Logging or audit testing.\n"
        "- Attach page.on('console', ...) and page.on('pageerror', ...) listeners before navigation.\n"
        "- Intercept logging endpoints and assert payloads in Python Playwright tests.\n"
        "- Keep log assertions user-visible and evidence-backed."
    ),
}

AUTH_TYPES: tuple[str, ...] = ("saml", "ntlm", "oidc", "basic", "logging", "none")


def get_template(auth_type: str) -> str | None:
    mapping = {
        "saml": SAML_AUTH_TEMPLATE,
        "ntlm": NTLM_AUTH_TEMPLATE,
        "oidc": OIDC_AUTH_TEMPLATE,
        "logging": LOGGING_FIXTURE_TEMPLATE,
    }
    return mapping.get(auth_type.lower())


def get_auth_hint(auth_type: str) -> str | None:
    return _AUTH_HINTS.get(auth_type.lower())
