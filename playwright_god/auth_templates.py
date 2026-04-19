"""Auth fixture templates for TypeScript Playwright tests."""

from __future__ import annotations

SAML_AUTH_TEMPLATE: str = """\
import { expect, type Page } from "@playwright/test";

export async function signInWithSaml(page: Page): Promise<void> {
  await page.goto(process.env.SP_LOGIN_URL ?? "https://app.example.com/saml/login");
  await page.getByLabel("Username").fill(process.env.TEST_USERNAME ?? "");
  await page.getByLabel("Password").fill(process.env.TEST_PASSWORD ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("https://app.example.com/home");
  await expect(page).toHaveURL("https://app.example.com/home");
}
"""

NTLM_AUTH_TEMPLATE: str = """\
import { type Browser, type BrowserContext } from "@playwright/test";

export async function authenticatedContext(browser: Browser): Promise<BrowserContext> {
  return browser.newContext({
    httpCredentials: {
      username: process.env.TEST_USERNAME ?? "",
      password: process.env.TEST_PASSWORD ?? "",
    },
  });
}
"""

OIDC_AUTH_TEMPLATE: str = """\
import { expect, type Page } from "@playwright/test";

export async function signInWithOidc(page: Page): Promise<void> {
  await page.goto(process.env.APP_LOGIN_URL ?? "https://app.example.com/auth/login");
  await page.getByLabel("Email").fill(process.env.TEST_USERNAME ?? "");
  await page.getByLabel("Password").fill(process.env.TEST_PASSWORD ?? "");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL("https://app.example.com/home");
  await expect(page).toHaveURL("https://app.example.com/home");
}
"""

LOGGING_FIXTURE_TEMPLATE: str = """\
import { type Page } from "@playwright/test";

export async function attachLogListeners(
  page: Page,
  messages: string[],
  errors: string[],
  auditRequests: string[],
): Promise<void> {
  await page.route("**/*", async (route) => {
    auditRequests.push(route.request().url());
    await route.continue();
  });

  page.on("console", (msg) => messages.push(`[${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (err) => errors.push(err.message));
}
"""

_AUTH_HINTS: dict[str, str] = {
    "saml": (
        "Auth type: SAML SSO.\n"
        "- Use helper functions or fixtures that navigate through the IdP and assert the post-login landing page.\n"
        "- Reference credentials through process.env values such as TEST_USERNAME and TEST_PASSWORD.\n"
        "- Use page.waitForURL() for redirect-heavy sign-in flows.\n"
        "- Preserve authenticated state for later tests when the workflow is expensive."
    ),
    "ntlm": (
        "Auth type: NTLM or Kerberos.\n"
        "- Use browser.newContext({ httpCredentials: ... }) in Playwright Test.\n"
        "- Reference credentials through process.env values.\n"
        "- Assert the page loads without redirecting back to login."
    ),
    "oidc": (
        "Auth type: OIDC authorization-code flow.\n"
        "- Model the provider redirect and callback in TypeScript Playwright fixtures.\n"
        "- Reference credentials through process.env values.\n"
        "- Keep MFA or consent steps explicit when the repository signals they are required."
    ),
    "basic": (
        "Auth type: HTTP Basic Authentication.\n"
        "- Use browser.newContext({ httpCredentials: ... }) and avoid hard-coded secrets."
    ),
    "logging": (
        "Logging or audit testing.\n"
        "- Attach page.on('console', ...) and page.on('pageerror', ...) listeners before navigation.\n"
        "- Intercept logging endpoints and assert payloads in TypeScript Playwright tests.\n"
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
