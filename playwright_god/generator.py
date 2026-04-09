"""Playwright test generator using LLM + RAG context.

Provides the following LLM backends:

* :class:`OpenAIClient` – calls the OpenAI Chat Completions API.
* :class:`AnthropicClient` – calls the Anthropic Claude API.
* :class:`GeminiClient` – calls the Google Gemini API.
* :class:`OllamaClient` – calls a locally running Ollama instance.
* :class:`TemplateLLMClient` – offline fallback; produces a useful skeleton
  Playwright test from the retrieved context without any API calls.
"""

from __future__ import annotations

import os
import re
import sys
import textwrap
from abc import ABC, abstractmethod
from typing import Callable, Sequence

from .auth_templates import get_auth_hint, get_template
from .indexer import RepositoryIndexer, SearchResult

# ---------------------------------------------------------------------------
# Credential-sanitization patterns
# ---------------------------------------------------------------------------

# Matches common assignment / literal patterns that look like hardcoded secrets.
# The replacement substitutes the matched value with a process.env reference.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # password = "..."  or  password: "..."
    (
        re.compile(
            r"""(password\s*[=:]\s*)(['"])([^'"]{4,})(\2)""",
            re.IGNORECASE,
        ),
        r"\1\2process.env.TEST_PASSWORD\2",
    ),
    # username = "..."  or  user = "..."
    (
        re.compile(
            r"""((?:username|user)\s*[=:]\s*)(['"])([^'"]{4,})(\2)""",
            re.IGNORECASE,
        ),
        r"\1\2process.env.TEST_USERNAME\2",
    ),
    # apiKey = "..."  or  api_key = "..."
    (
        re.compile(
            r"""(api[_-]?key\s*[=:]\s*)(['"])([^'"]{8,})(\2)""",
            re.IGNORECASE,
        ),
        r"\1\2process.env.API_KEY\2",
    ),
    # token = "..."  or  accessToken = "..."
    (
        re.compile(
            r"""((?:access_?)?token\s*[=:]\s*)(['"])([^'"]{8,})(\2)""",
            re.IGNORECASE,
        ),
        r"\1\2process.env.ACCESS_TOKEN\2",
    ),
    # secret = "..."
    (
        re.compile(
            r"""(secret\s*[=:]\s*)(['"])([^'"]{4,})(\2)""",
            re.IGNORECASE,
        ),
        r"\1\2process.env.SECRET\2",
    ),
]

# Values that look like placeholders / env-var references — never redact these.
_SAFE_VALUES: re.Pattern[str] = re.compile(
    r"process\.env\.|<[A-Z_]+>|YOUR_|PLACEHOLDER|EXAMPLE|CHANGE_ME",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# LLM client abstraction
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    """Abstract base class for LLM completion backends."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return its text response."""


class OpenAIClient(LLMClient):
    """Calls the OpenAI Chat Completions API.

    Parameters
    ----------
    api_key:
        OpenAI API key.  Falls back to the ``OPENAI_API_KEY`` environment
        variable if *None*.
    model:
        Model name (default ``gpt-4o``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o",
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIClient. "
                "Install it with: pip install openai"
            ) from exc

        import openai

        self._client = openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", "")
        )
        self.model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": PlaywrightTestGenerator.SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    """Calls the Anthropic Claude API.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Falls back to the ``ANTHROPIC_API_KEY``
        environment variable if *None*.
    model:
        Model name (default ``claude-3-5-sonnet-20241022``).
    max_tokens:
        Maximum number of tokens to generate (default ``4096``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
    ) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "anthropic is required for AnthropicClient. "
                "Install it with: pip install anthropic"
            ) from exc

        import anthropic

        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=PlaywrightTestGenerator.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class GeminiClient(LLMClient):
    """Calls the Google Gemini API.

    Parameters
    ----------
    api_key:
        Google API key.  Falls back to the ``GOOGLE_API_KEY`` environment
        variable if *None*.
    model:
        Model name (default ``gemini-1.5-pro``).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-1.5-pro",
    ) -> None:
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "google-generativeai is required for GeminiClient. "
                "Install it with: pip install google-generativeai"
            ) from exc

        import google.generativeai as genai

        genai.configure(api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""))
        self._client = genai.GenerativeModel(
            model_name=model,
            system_instruction=PlaywrightTestGenerator.SYSTEM_PROMPT,
        )

    def complete(self, prompt: str) -> str:
        response = self._client.generate_content(prompt)
        return response.text


class OllamaClient(LLMClient):
    """Calls a locally running Ollama instance via its REST API.

    Parameters
    ----------
    model:
        Model name served by Ollama (default ``llama3``).
    base_url:
        Base URL of the Ollama server (default ``http://localhost:11434``).
    """

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
    ) -> None:
        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "requests is required for OllamaClient. "
                "Install it with: pip install requests"
            ) from exc

        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str) -> str:
        import requests

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": PlaywrightTestGenerator.SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


class TemplateLLMClient(LLMClient):
    """Offline template-based fallback that does not require an LLM API.

    Generates a syntactically valid Playwright test skeleton based on the
    context chunks retrieved from the repository index.  The generated test
    will need human review but gives a concrete starting point.
    """

    # Keywords that signal the test should include log/audit assertions.
    _LOG_KEYWORDS: frozenset[str] = frozenset(
        {
            "logging", "log", "audit", "audit trail", "audit log",
            "console output", "console log", "error log", "pageerror",
            "analytics", "telemetry", "splunk", "datadog",
        }
    )

    def complete(self, prompt: str) -> str:  # noqa: PLR0914
        """Parse *prompt* and return a template Playwright test."""
        description = self._extract_description(prompt)
        urls = self._extract_urls(prompt)
        selectors = self._extract_selectors(prompt)
        text_content = self._extract_text_content(prompt)
        form_fields = self._extract_form_fields(prompt)
        is_log_test = self._is_logging_description(description + " " + prompt)

        base_url = urls[0] if urls else "http://localhost:3000"
        test_name = self._slugify(description)

        lines = [
            "import { test, expect } from '@playwright/test';",
            "",
            f"// Generated test for: {description}",
            "// Review and adjust selectors, URLs and assertions before running.",
            "",
            f"test.describe('{test_name}', () => {{",
        ]

        # Navigation test
        lines += [
            f"  test('navigates to the correct page', async ({{ page }}) => {{",
            f"    await page.goto('{base_url}');",
        ]
        if text_content:
            for text in text_content[:3]:
                lines.append(f"    await expect(page.getByText('{text}')).toBeVisible();")
        else:
            lines.append(f"    await expect(page).toHaveURL('{base_url}');")
        lines += ["  });", ""]

        # Selector-based interaction tests
        if selectors:
            lines += [
                "  test('interacts with key elements', async ({ page }) => {",
                f"    await page.goto('{base_url}');",
            ]
            for sel in selectors[:5]:
                lines.append(f"    await expect(page.locator('{sel}')).toBeVisible();")
            lines += ["  });", ""]

        # Form test (if form fields detected)
        if form_fields:
            lines += [
                "  test('fills and submits form', async ({ page }) => {",
                f"    await page.goto('{base_url}');",
            ]
            for label, value in form_fields[:4]:
                lines.append(
                    f"    await page.getByLabel('{label}').fill('{value}');"
                )
            lines += [
                "    await page.getByRole('button', { name: /submit/i }).click();",
                "  });",
                "",
            ]

        # Log / audit assertion tests
        if is_log_test:
            lines += [
                "  // ── Console log assertions ────────────────────────────────────",
                "  test('captures expected console messages', async ({ page }) => {",
                "    const messages: string[] = [];",
                "    page.on('console', (msg) => messages.push(`[${msg.type()}] ${msg.text()}`));",
                f"    await page.goto('{base_url}');",
                "    // TODO: trigger the action that should emit a log, then assert:",
                "    // expect(messages.some((m) => m.includes('expected message'))).toBe(true);",
                "    expect(messages).toBeDefined();",
                "  });",
                "",
                "  // ── No uncaught errors ────────────────────────────────────────",
                "  test('has no uncaught JavaScript errors', async ({ page }) => {",
                "    const errors: string[] = [];",
                "    page.on('pageerror', (err) => errors.push(err.message));",
                f"    await page.goto('{base_url}');",
                "    expect(errors).toHaveLength(0);",
                "  });",
                "",
                "  // ── Audit / logging API intercept ────────────────────────────",
                "  test('sends an audit event to the log endpoint', async ({ page }) => {",
                "    const logRequests: string[] = [];",
                "    await page.route('**/api/audit**', async (route) => {",
                "      logRequests.push(route.request().postData() ?? '');",
                "      await route.continue();",
                "    });",
                f"    await page.goto('{base_url}');",
                "    // TODO: trigger the auditable action, then assert:",
                "    // expect(logRequests.length).toBeGreaterThan(0);",
                "    // expect(logRequests[0]).toContain('expected-event');",
                "  });",
                "",
            ]

        lines += ["});", ""]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_description(prompt: str) -> str:
        m = re.search(r"Description:\s*(.+?)(?:\n|Context:|$)", prompt, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return "application behaviour"

    @staticmethod
    def _extract_urls(prompt: str) -> list[str]:
        return re.findall(r"https?://[^\s\"'<>]+", prompt)

    @staticmethod
    def _extract_selectors(prompt: str) -> list[str]:
        """Extract CSS selectors, IDs, and class names found in the context."""
        patterns = [
            r'(?:getElementById|querySelector|querySelectorAll)\s*\(\s*["\']([^"\']+)["\']',
            r'id=["\']([^"\']+)["\']',
            r'class=["\']([^"\']+)["\']',
            r'data-testid=["\']([^"\']+)["\']',
        ]
        found: list[str] = []
        for pattern in patterns:
            for match in re.findall(pattern, prompt):
                selector = match.strip()
                if selector and selector not in found:
                    found.append(selector)
        return found

    @staticmethod
    def _extract_text_content(prompt: str) -> list[str]:
        """Extract visible text strings (headings, button labels, etc.)."""
        found = re.findall(r"<h[1-6][^>]*>([^<]+)</h[1-6]>", prompt, re.IGNORECASE)
        found += re.findall(r"<button[^>]*>([^<]+)</button>", prompt, re.IGNORECASE)
        found += re.findall(r"<a[^>]*>([^<]+)</a>", prompt, re.IGNORECASE)
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for item in found:
            clean = item.strip()
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)
        return result

    @staticmethod
    def _extract_form_fields(prompt: str) -> list[tuple[str, str]]:
        """Return (label, placeholder_value) pairs for form inputs."""
        labels = re.findall(
            r"<label[^>]*>([^<]+)</label>",
            prompt,
            re.IGNORECASE,
        )
        inputs = re.findall(
            r'<input[^>]*placeholder=["\']([^"\']*)["\']',
            prompt,
            re.IGNORECASE,
        )
        pairs: list[tuple[str, str]] = []
        for label in labels:
            label = label.strip()
            placeholder = inputs[len(pairs)] if len(pairs) < len(inputs) else "value"
            pairs.append((label, placeholder or "value"))
        return pairs

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", " ", text).strip()

    @classmethod
    def _is_logging_description(cls, text: str) -> bool:
        """Return ``True`` when *text* contains logging / audit-related keywords."""
        lower = text.lower()
        return any(kw in lower for kw in cls._LOG_KEYWORDS)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class PlaywrightTestGenerator:
    """Generates Playwright tests by combining RAG context with an LLM.

    Parameters
    ----------
    llm_client:
        An :class:`LLMClient` instance.  Defaults to
        :class:`TemplateLLMClient` (no API key required).
    indexer:
        A :class:`~playwright_god.indexer.RepositoryIndexer` that has
        already been populated via
        :meth:`~playwright_god.indexer.RepositoryIndexer.add_chunks`.
    n_context:
        Default number of context chunks to retrieve per query.
    """

    SYSTEM_PROMPT = textwrap.dedent(
        """\
        You are an expert Playwright test engineer.
        Your task is to write high-quality Playwright tests in TypeScript.

        Guidelines:
        - Use @playwright/test with modern locator APIs (getByRole, getByText, getByLabel, etc.)
        - Prefer user-visible attributes over CSS selectors or XPath
        - Each test should be independent and idempotent
        - Use test.describe blocks to group related tests
        - Add await/async correctly
        - Include meaningful assertions using expect()
        - Add a brief comment explaining each test's intent
        - Return only the TypeScript code, no markdown fences

        Authentication guidelines:
        - NEVER hardcode passwords, tokens, or API keys — always use process.env.TEST_USERNAME,
          process.env.TEST_PASSWORD, or a dedicated env variable
        - For SAML / OIDC SSO: use a global-setup.ts that completes the login flow once and
          calls page.context().storageState({ path }) to persist the session; reference that
          file in playwright.config.ts via storageState
        - Use page.waitForURL() to handle multi-step SSO redirect chains (SP → IdP → callback)
        - For NTLM / Kerberos (Active Directory): use httpCredentials on the browser context;
          Playwright negotiates the NTLM handshake automatically
        - For OIDC authorization-code flow: wait for the provider redirect, fill the login
          form, wait for the callback URL, then capture storageState

        Logging / audit trail guidelines:
        - Attach page.on('console', ...) listeners before navigation to capture log messages
        - Attach page.on('pageerror', ...) listeners and assert the resulting array is empty
        - Use page.route() to intercept calls to logging/analytics/audit endpoints and assert
          they receive the expected payload
        """
    )

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        indexer: RepositoryIndexer | None = None,
        n_context: int = 10,
    ) -> None:
        self.llm_client: LLMClient = llm_client or TemplateLLMClient()
        self.indexer = indexer
        self.n_context = n_context

    def generate(
        self,
        description: str,
        extra_context: str | None = None,
        auth_type: str | None = None,
        redact_secrets: bool = True,
    ) -> str:
        """Generate a Playwright test for the given *description*.

        Parameters
        ----------
        description:
            Human-readable description of what to test (e.g. "user login
            flow on the /login page").
        extra_context:
            Any additional context to append to the prompt (e.g. a manual
            code snippet or notes).
        auth_type:
            Authentication mechanism used by the system under test.  When
            provided the relevant auth hint and TypeScript template snippet are
            injected into the prompt so the LLM produces correct auth code.
            Accepted values: ``"saml"``, ``"ntlm"``, ``"oidc"``, ``"basic"``,
            ``"logging"``, ``"none"`` (or ``None`` to skip).
        redact_secrets:
            When ``True`` (default) a post-generation sanitization pass
            replaces patterns that look like hardcoded credentials with
            ``process.env.*`` placeholders and prints a warning to stderr.

        Returns
        -------
        str
            TypeScript Playwright test code.
        """
        context_chunks: list[SearchResult] = []
        if self.indexer is not None:
            context_chunks = self.indexer.search(description, n_results=self.n_context)

        # Build auth-specific extra context to inject alongside any caller-
        # supplied extra_context.
        auth_extra: str | None = None
        if auth_type and auth_type.lower() != "none":
            parts: list[str] = []
            hint = get_auth_hint(auth_type)
            if hint:
                parts.append(hint)
            template = get_template(auth_type)
            if template:
                parts.append(
                    "Reference TypeScript template:\n"
                    "```typescript\n"
                    + template
                    + "```"
                )
            if parts:
                auth_extra = "\n\n".join(parts)

        combined_extra: str | None
        if auth_extra and extra_context:
            combined_extra = auth_extra + "\n\n" + extra_context
        elif auth_extra:
            combined_extra = auth_extra
        else:
            combined_extra = extra_context

        prompt = self._build_prompt(description, context_chunks, combined_extra)
        result = self.llm_client.complete(prompt)

        if redact_secrets:
            result = self._redact_secrets(result)

        return result

    @staticmethod
    def _redact_secrets(code: str) -> str:
        """Replace hardcoded credential literals with process.env.* references.

        Patterns that already reference env vars, use placeholder text, or are
        shorter than the minimum match length are left untouched.
        """
        redacted = False

        def _make_replacer(replacement: str) -> Callable[[re.Match[str]], str]:
            def _replace(m: re.Match[str]) -> str:
                nonlocal redacted
                value = m.group(3)
                if _SAFE_VALUES.search(value):
                    return m.group(0)
                redacted = True
                return m.expand(replacement)
            return _replace

        for pattern, replacement in _SECRET_PATTERNS:
            code = pattern.sub(_make_replacer(replacement), code)

        if redacted:
            print(
                "playwright-god: WARNING – hardcoded credentials were detected in the "
                "generated output and replaced with process.env.* placeholders. "
                "Store secrets in environment variables, never in test code.",
                file=sys.stderr,
            )
        return code

    def _build_prompt(
        self,
        description: str,
        context: Sequence[SearchResult],
        extra_context: str | None,
    ) -> str:
        """Build the full prompt string."""
        parts: list[str] = [
            f"Description: {description}",
            "",
        ]

        if context:
            parts += [
                "Context (relevant repository code):",
                "=" * 60,
            ]
            for result in context:
                c = result.chunk
                parts += [
                    f"--- {c.file_path} (lines {c.start_line}-{c.end_line}, "
                    f"score={result.score:.3f}) ---",
                    c.content,
                    "",
                ]

        if extra_context:
            parts += [
                "Additional context:",
                "=" * 60,
                extra_context,
                "",
            ]

        parts += [
            "=" * 60,
            "Write a comprehensive Playwright test suite for the description above.",
            "Use the context to understand the application structure and selectors.",
        ]

        return "\n".join(parts)
