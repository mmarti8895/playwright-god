"""Auth fixture templates for Playwright tests.

Provides ready-to-use TypeScript code snippets for common authentication
mechanisms so the LLM has concrete, correct patterns to follow:

* :data:`SAML_AUTH_TEMPLATE` – SAML SSO global-setup with storageState capture.
* :data:`NTLM_AUTH_TEMPLATE` – NTLM / Kerberos via ``httpCredentials``.
* :data:`OIDC_AUTH_TEMPLATE` – OIDC authorization-code flow with storageState.
* :data:`LOGGING_FIXTURE_TEMPLATE` – Console/error event listeners + XHR intercept.

The module also exposes :func:`get_template` for convenient lookup by auth type
and :func:`get_auth_hint` for the short natural-language hint injected into the
LLM prompt.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TypeScript snippet constants
# ---------------------------------------------------------------------------

SAML_AUTH_TEMPLATE: str = """\
// ── SAML SSO global-setup.ts ──────────────────────────────────────────────
// Runs once before the test suite.  Navigates to the SP-initiated login URL,
// follows the redirect to the IdP, submits credentials, waits for the
// callback, then captures the authenticated browser state.
//
// Usage: set playwrightConfig.globalSetup = './global-setup.ts'
//        and pass storageState to each project that needs auth.

import { chromium, FullConfig } from '@playwright/test';

const SP_LOGIN_URL  = process.env.SP_LOGIN_URL  ?? 'https://app.example.com/saml/login';
const IDP_LOGIN_URL = process.env.IDP_LOGIN_URL ?? 'https://idp.example.com/login';
const USERNAME      = process.env.TEST_USERNAME ?? '';
const PASSWORD      = process.env.TEST_PASSWORD ?? '';
const STATE_FILE    = 'playwright/.auth/saml-state.json';

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const browser = await chromium.launch();
  const page    = await browser.newPage();

  // 1. Initiate SP-side SSO – browser is redirected to the IdP.
  await page.goto(SP_LOGIN_URL);
  await page.waitForURL(IDP_LOGIN_URL + '**');

  // 2. Fill IdP login form.
  await page.getByLabel('Username').fill(USERNAME);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();

  // 3. Wait for the SP callback / post-SSO landing page.
  await page.waitForURL(SP_LOGIN_URL.replace('/saml/login', '/**'));

  // 4. Persist the authenticated session for re-use across tests.
  await page.context().storageState({ path: STATE_FILE });
  await browser.close();
}
"""

NTLM_AUTH_TEMPLATE: str = """\
// ── NTLM / Windows Integrated Authentication ──────────────────────────────
// Active Directory sites that rely on NTLM or Kerberos can be tested by
// supplying httpCredentials when creating the browser context.  Playwright
// negotiates the NTLM handshake automatically.
//
// In playwright.config.ts:
//   use: {
//     httpCredentials: {
//       username: process.env.TEST_USERNAME ?? '',
//       password: process.env.TEST_PASSWORD ?? '',
//     },
//   }

import { test, expect } from '@playwright/test';

// Override credentials per-test if needed:
test.use({
  httpCredentials: {
    username: process.env.TEST_USERNAME ?? '',
    password: process.env.TEST_PASSWORD ?? '',
  },
});

test('authenticated NTLM page loads', async ({ page }) => {
  await page.goto(process.env.APP_URL ?? 'https://intranet.example.com');
  // After NTLM negotiation the page should render without a 401.
  await expect(page).not.toHaveURL(/[/]login/);
  await expect(page.getByRole('main')).toBeVisible();
});
"""

OIDC_AUTH_TEMPLATE: str = """\
// ── OIDC Authorization-Code Flow global-setup.ts ──────────────────────────
// Works for any OIDC provider (Azure AD, Okta, Auth0, Keycloak, etc.).
// Navigates to the app's login trigger, completes the provider's login form,
// waits for the callback redirect, and stores the browser state.

import { chromium, FullConfig } from '@playwright/test';

const APP_LOGIN_URL   = process.env.APP_LOGIN_URL   ?? 'https://app.example.com/auth/login';
const OIDC_ORIGIN     = process.env.OIDC_ORIGIN     ?? 'https://login.microsoftonline.com';
const USERNAME        = process.env.TEST_USERNAME   ?? '';
const PASSWORD        = process.env.TEST_PASSWORD   ?? '';
const STATE_FILE      = 'playwright/.auth/oidc-state.json';

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const browser = await chromium.launch();
  const page    = await browser.newPage();

  // 1. Navigate to the app – it redirects to the OIDC provider.
  await page.goto(APP_LOGIN_URL);
  await page.waitForURL(OIDC_ORIGIN + '/**');

  // 2. Complete provider login.
  await page.getByPlaceholder(/email|username/i).fill(USERNAME);
  await page.getByRole('button', { name: /next|continue/i }).click();
  await page.getByPlaceholder(/password/i).fill(PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();

  // 3. Handle MFA / consent prompts if present.
  // await page.getByRole('button', { name: /yes|allow|accept/i }).click();

  // 4. Wait until the app's post-login page is reached.
  await page.waitForURL(APP_LOGIN_URL.replace('/auth/login', '/**'));

  // 5. Persist the authenticated session.
  await page.context().storageState({ path: STATE_FILE });
  await browser.close();
}
"""

LOGGING_FIXTURE_TEMPLATE: str = """\
// ── Logging & error assertion helpers ─────────────────────────────────────
// Attach console listeners and network intercepts to validate that the
// application emits expected log messages and never fires uncaught errors.

import { test, expect } from '@playwright/test';

// ── 1. Capture and assert console messages ──────────────────────────────
test.describe('console logging', () => {
  test('emits expected log message on action', async ({ page }) => {
    const messages: string[] = [];
    page.on('console', (msg) => messages.push(`[${msg.type()}] ${msg.text()}`));

    await page.goto(process.env.APP_URL ?? 'http://localhost:3000');
    await page.getByRole('button', { name: /submit/i }).click();

    // Assert a specific log was emitted.
    expect(messages.some((m) => m.includes('form submitted'))).toBe(true);
  });

  // ── 2. Fail on uncaught page errors ──────────────────────────────────
  test('has no uncaught JavaScript errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));

    await page.goto(process.env.APP_URL ?? 'http://localhost:3000');

    expect(errors).toHaveLength(0);
  });
});

// ── 3. Intercept log/audit API calls ─────────────────────────────────────
test.describe('audit log API', () => {
  test('POSTs an audit event when a sensitive action is performed', async ({ page }) => {
    const logRequests: string[] = [];

    await page.route('**/api/audit**', async (route) => {
      logRequests.push(route.request().postData() ?? '');
      await route.continue();
    });

    await page.goto(process.env.APP_URL ?? 'http://localhost:3000');
    await page.getByRole('button', { name: /delete/i }).click();

    expect(logRequests.length).toBeGreaterThan(0);
    expect(logRequests[0]).toContain('delete');
  });
});
"""

# ---------------------------------------------------------------------------
# Short auth-type hint strings injected directly into the LLM prompt
# ---------------------------------------------------------------------------

_AUTH_HINTS: dict[str, str] = {
    "saml": (
        "Auth type: SAML SSO.\n"
        "- Use a global-setup.ts that navigates to the SP login URL, follows the "
        "IdP redirect, fills credentials, and calls storageState({ path }) to "
        "capture the session.\n"
        "- In tests, pass storageState to the browser context so every test starts "
        "already authenticated.\n"
        "- Use page.waitForURL() to handle the multi-step SP→IdP→callback redirect chain.\n"
        "- Reference credentials as process.env.TEST_USERNAME and process.env.TEST_PASSWORD."
    ),
    "ntlm": (
        "Auth type: NTLM / Windows Integrated Authentication (Active Directory).\n"
        "- Supply httpCredentials: { username, password } when creating the browser "
        "context or via playwright.config.ts use.httpCredentials.\n"
        "- Playwright negotiates the NTLM/Kerberos handshake automatically.\n"
        "- Reference credentials as process.env.TEST_USERNAME and process.env.TEST_PASSWORD.\n"
        "- After navigation the page should render without a 401 redirect to /login."
    ),
    "oidc": (
        "Auth type: OIDC (OpenID Connect) authorization-code flow.\n"
        "- Use a global-setup.ts that navigates to the app login URL, completes the "
        "provider login form, and calls storageState({ path }) after the callback redirect.\n"
        "- Use page.waitForURL() to wait for the OIDC provider redirect and then the "
        "post-login callback.\n"
        "- Reference credentials as process.env.TEST_USERNAME and process.env.TEST_PASSWORD.\n"
        "- Handle optional MFA/consent prompts with conditional clicks."
    ),
    "basic": (
        "Auth type: HTTP Basic Authentication.\n"
        "- Supply httpCredentials: { username, password } on the browser context.\n"
        "- Reference credentials as process.env.TEST_USERNAME and process.env.TEST_PASSWORD."
    ),
    "logging": (
        "Logging / audit trail testing.\n"
        "- Attach page.on('console', ...) listeners before navigation to capture log output.\n"
        "- Attach page.on('pageerror', ...) listeners and assert the array is empty at the "
        "end of each test.\n"
        "- Use page.route() to intercept HTTP calls to logging/analytics endpoints and "
        "assert they are called with the expected payload.\n"
        "- Use expect(messages).toContain(...) or .some() to assert specific log messages."
    ),
}

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

#: All valid auth-type identifiers.
AUTH_TYPES: tuple[str, ...] = ("saml", "ntlm", "oidc", "basic", "logging", "none")


def get_template(auth_type: str) -> str | None:
    """Return the TypeScript snippet for *auth_type*, or ``None`` for unknown types.

    Parameters
    ----------
    auth_type:
        One of ``"saml"``, ``"ntlm"``, ``"oidc"``, ``"logging"``.
        Returns ``None`` for ``"basic"``, ``"none"``, or unrecognised values
        (basic auth has no multi-step setup snippet; it is covered by the hint).
    """
    mapping = {
        "saml": SAML_AUTH_TEMPLATE,
        "ntlm": NTLM_AUTH_TEMPLATE,
        "oidc": OIDC_AUTH_TEMPLATE,
        "logging": LOGGING_FIXTURE_TEMPLATE,
    }
    return mapping.get(auth_type.lower())


def get_auth_hint(auth_type: str) -> str | None:
    """Return the short natural-language auth hint for *auth_type*.

    Returns ``None`` for ``"none"`` or unrecognised values.
    """
    return _AUTH_HINTS.get(auth_type.lower())
