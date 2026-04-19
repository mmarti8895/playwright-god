"""Playwright test generator using LLM + RAG context."""

from __future__ import annotations

import os
import re
import sys
import textwrap
from abc import ABC, abstractmethod
from typing import Callable, Sequence

from .auth_templates import get_auth_hint, get_template
from .indexer import RepositoryIndexer, SearchResult

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"""(password\s*[=:]\s*)(['"])([^'"]{4,})(\2)""", re.IGNORECASE),
        r'\1process.env.TEST_PASSWORD ?? ""',
    ),
    (
        re.compile(r"""((?:username|user)\s*[=:]\s*)(['"])([^'"]{4,})(\2)""", re.IGNORECASE),
        r'\1process.env.TEST_USERNAME ?? ""',
    ),
    (
        re.compile(r"""(api[_-]?key\s*[=:]\s*)(['"])([^'"]{8,})(\2)""", re.IGNORECASE),
        r'\1process.env.API_KEY ?? ""',
    ),
    (
        re.compile(r"""((?:access_?)?token\s*[=:]\s*)(['"])([^'"]{8,})(\2)""", re.IGNORECASE),
        r'\1process.env.ACCESS_TOKEN ?? ""',
    ),
    (
        re.compile(r"""(secret\s*[=:]\s*)(['"])([^'"]{4,})(\2)""", re.IGNORECASE),
        r'\1process.env.SECRET ?? ""',
    ),
]

_SAFE_VALUES: re.Pattern[str] = re.compile(
    r"os\.environ|getenv|process\.env|<[A-Z_]+>|YOUR_|PLACEHOLDER|EXAMPLE|CHANGE_ME",
    re.IGNORECASE,
)


class LLMClient(ABC):
    """Abstract base class for LLM completion backends."""

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Send *prompt* to the LLM and return its text response."""


class OpenAIClient(LLMClient):
    """Calls the OpenAI Chat Completions API."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o") -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIClient. Install it with: pip install openai"
            ) from exc

        import openai

        self._client = openai.OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))
        self.model = model

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        sys_msg = system_prompt or PlaywrightTestGenerator.SYSTEM_PROMPT
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    """Calls the Anthropic Claude API."""

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
                "anthropic is required for AnthropicClient. Install it with: pip install anthropic"
            ) from exc

        import anthropic

        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        sys_msg = system_prompt or PlaywrightTestGenerator.SYSTEM_PROMPT
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=sys_msg,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class GeminiClient(LLMClient):
    """Calls the Google Gemini API."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-1.5-pro") -> None:
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "google-generativeai is required for GeminiClient. Install it with: pip install google-generativeai"
            ) from exc

        import google.generativeai as genai

        genai.configure(api_key=api_key or os.environ.get("GOOGLE_API_KEY", ""))
        self._model_name = model
        self._client = genai.GenerativeModel(
            model_name=model,
            system_instruction=PlaywrightTestGenerator.SYSTEM_PROMPT,
        )
        self._model_cache: dict[str, "genai.GenerativeModel"] = {}  # type: ignore[name-defined]

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if system_prompt is None:
            client = self._client
        else:
            if system_prompt not in self._model_cache:
                import google.generativeai as genai

                self._model_cache[system_prompt] = genai.GenerativeModel(
                    model_name=self._model_name,
                    system_instruction=system_prompt,
                )
            client = self._model_cache[system_prompt]
        response = client.generate_content(prompt)
        return response.text


class OllamaClient(LLMClient):
    """Calls a locally running Ollama instance via its REST API."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434") -> None:
        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "requests is required for OllamaClient. Install it with: pip install requests"
            ) from exc

        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        import requests

        sys_msg = system_prompt or PlaywrightTestGenerator.SYSTEM_PROMPT
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_msg},
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
    """Offline fallback that emits TypeScript Playwright tests."""

    _LOG_KEYWORDS: frozenset[str] = frozenset(
        {
            "logging",
            "log",
            "audit",
            "audit trail",
            "audit log",
            "console output",
            "console log",
            "error log",
            "pageerror",
            "analytics",
            "telemetry",
            "splunk",
            "datadog",
        }
    )

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:  # noqa: ARG002
        if self._is_plan_prompt(prompt):
            return self._generate_plan(prompt)

        description = self._extract_description(prompt)
        urls = self._extract_urls(prompt)
        selectors = self._extract_selectors(prompt)
        text_content = self._extract_text_content(prompt)
        form_fields = self._extract_form_fields(prompt)
        is_log_test = self._is_logging_description(f"{description} {prompt}")

        base_url = urls[0] if urls else "http://localhost:3000"
        primary_test_name = self._test_name(description, "covers_described_flow")

        lines = [
            'import { test, expect } from "@playwright/test";',
            "",
            f'const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "{base_url}";',
            "",
            f"// Generated test for: {description}",
            "// Review selectors, data setup, and assertions before running.",
            "",
            f'test("{primary_test_name}", async ({{ page }}) => {{',
            "  // Validate the primary user journey described in the prompt.",
            "  await page.goto(BASE_URL);",
        ]

        if text_content:
            for text in text_content[:3]:
                safe_text = text.replace('"', '\\"')
                lines.append(f'  await expect(page.getByText("{safe_text}")).toBeVisible();')
        else:
            lines.append("  await expect(page).toHaveURL(BASE_URL);")
        lines.extend(["});", ""])

        if selectors:
            lines.extend(
                [
                    'test("key ui elements are visible", async ({ page }) => {',
                    "  // Check that the most relevant elements inferred from the repository are visible.",
                    "  await page.goto(BASE_URL);",
                ]
            )
            for selector in selectors[:5]:
                safe_selector = selector.replace('"', '\\"')
                lines.append(f'  await expect(page.locator("{safe_selector}")).toBeVisible();')
            lines.extend(["});", ""])

        if form_fields:
            lines.extend(
                [
                    'test("form submission flow", async ({ page }) => {',
                    "  // Exercise the main form inputs inferred from the repository context.",
                    "  await page.goto(BASE_URL);",
                ]
            )
            for label, value in form_fields[:4]:
                safe_label = label.replace('"', '\\"')
                safe_value = value.replace('"', '\\"')
                lines.append(f'  await page.getByLabel("{safe_label}").fill("{safe_value}");')
            lines.append(
                '  await page.getByRole("button", { name: /submit|login|sign in|add|save/i }).click();'
            )
            lines.extend(["});", ""])

        if is_log_test:
            lines.extend(
                [
                    'test("console and logging signals are observable", async ({ page }) => {',
                    "  // Capture observable logging signals before navigation so failures are reviewable.",
                    "  const messages: string[] = [];",
                    "  const errors: string[] = [];",
                    "  const auditRequests: string[] = [];",
                    "",
                    "  await page.route(\"**/*\", async (route) => {",
                    "    auditRequests.push(route.request().url());",
                    "    await route.continue();",
                    "  });",
                    "",
                    '  page.on("console", (msg) => messages.push(`[${msg.type()}] ${msg.text()}`));',
                    '  page.on("pageerror", (err) => errors.push(err.message));',
                    "  await page.goto(BASE_URL);",
                    "  expect(errors).toEqual([]);",
                    "  expect(messages).toBeDefined();",
                    "  expect(auditRequests).toBeDefined();",
                    "});",
                    "",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _is_plan_prompt(prompt: str) -> bool:
        lower = prompt.lower()
        return (
            lower.strip().startswith("generate a markdown test plan")
            or (
                "below is a memory map of the indexed repository" in lower
                and "generate a markdown test plan" in lower
            )
        )

    @staticmethod
    def _generate_plan(prompt: str) -> str:
        file_paths = re.findall(
            r"^(\S+\.(?:ts|tsx|js|jsx|py|html|vue|svelte))\s+\[",
            prompt,
            re.MULTILINE,
        )
        focus_match = re.search(r"Focus area:\s*(.+)", prompt, re.IGNORECASE)
        focus = focus_match.group(1).strip() if focus_match else None

        lines = [
            "# Playwright Test Plan",
            "",
            "> Generated by playwright-god (offline template mode).",
            "> Review confidence, selectors, and setup assumptions before implementation.",
            "",
        ]
        if focus:
            lines += [f"**Focus area:** {focus}", ""]

        if file_paths:
            lines += ["## Suggested test scenarios", ""]
            for path in file_paths[:10]:
                name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                lines += [
                    f"### `{path}`",
                    "",
                    f"- [ ] `{name}` renders without errors",
                    f"- [ ] `{name}` interactive elements remain user-visible",
                    f"- [ ] `{name}` handles edge-case inputs gracefully",
                    "",
                ]
        else:
            lines += [
                "## Suggested test scenarios",
                "",
                "- [ ] Home page loads and key elements are visible",
                "- [ ] Navigation links route to the correct pages",
                "- [ ] Forms validate input and display error messages",
                "- [ ] Authenticated routes redirect unauthenticated users",
                "- [ ] Audit and error states are observable in the UI",
                "",
            ]

        lines += [
            "## General cross-cutting scenarios",
            "",
            "- [ ] All pages pass basic accessibility checks",
            "- [ ] No uncaught JavaScript errors appear on page load",
            "- [ ] Responsive layout renders correctly at mobile and desktop widths",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _extract_description(prompt: str) -> str:
        match = re.search(
            r"Description:\s*(.+?)(?:\n|Context:|Additional context:|$)",
            prompt,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return "application behaviour"

    @staticmethod
    def _extract_urls(prompt: str) -> list[str]:
        return re.findall(r"https?://[^\s\"'<>]+", prompt)

    @staticmethod
    def _extract_selectors(prompt: str) -> list[str]:
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
        found = re.findall(r"<h[1-6][^>]*>([^<]+)</h[1-6]>", prompt, re.IGNORECASE)
        found += re.findall(r"<button[^>]*>([^<]+)</button>", prompt, re.IGNORECASE)
        found += re.findall(r"<a[^>]*>([^<]+)</a>", prompt, re.IGNORECASE)
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
        labels = re.findall(r"<label[^>]*>([^<]+)</label>", prompt, re.IGNORECASE)
        inputs = re.findall(
            r'<input[^>]*placeholder=["\']([^"\']*)["\']',
            prompt,
            re.IGNORECASE,
        )
        pairs: list[tuple[str, str]] = []
        for label in labels:
            placeholder = inputs[len(pairs)] if len(pairs) < len(inputs) else "value"
            pairs.append((label.strip(), placeholder or "value"))
        return pairs

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", " ", text).strip()

    @classmethod
    def _test_name(cls, description: str, fallback: str) -> str:
        slug = cls._slugify(description).lower().split()
        if not slug:
            return f"test_{fallback}"
        return "test_" + "_".join(slug[:6])

    @classmethod
    def _is_logging_description(cls, text: str) -> bool:
        lower = text.lower()
        return any(keyword in lower for keyword in cls._LOG_KEYWORDS)


class PlaywrightTestGenerator:
    """Generates Playwright tests by combining RAG context with an LLM."""

    PLAN_SYSTEM_PROMPT = textwrap.dedent(
        """\
        You are an expert Playwright test engineer and QA architect.
        Your task is to analyze a repository's code structure and propose a
        comprehensive Playwright end-to-end test plan.

        Guidelines:
        - Group suggested tests by feature area or page/route
        - For each area propose 2-5 specific, actionable test scenarios
        - Name each scenario in plain English
        - Note selectors, routes, API endpoints, and confidence signals when the repository reveals them
        - Flag areas that may require special setup such as auth state or mocked APIs
        - Output a clean Markdown document
        """
    )

    SYSTEM_PROMPT = textwrap.dedent(
        """\
        You are an expert Playwright test engineer.
        Your task is to write high-quality Playwright tests in TypeScript.

        Guidelines:
        - Use Playwright Test in TypeScript
        - Prefer user-visible attributes over CSS selectors or XPath
        - Each test should be independent and idempotent
        - Use import { test, expect } from "@playwright/test"
        - Include meaningful assertions using await expect(...)
        - Add a brief comment explaining each test's intent
        - Reflect repository evidence and uncertainty where the prompt signals ambiguity
        - Return only TypeScript code, no markdown fences
        - Produce tests that fit naturally in a .spec.ts file

        Authentication guidelines:
        - NEVER hardcode passwords, tokens, or API keys; always use process.env values
        - For SAML and OIDC flows, model reusable helper functions or fixtures
        - Use page.waitForURL() to handle redirect chains
        - For NTLM or Kerberos flows, use httpCredentials on the browser context

        Logging guidelines:
        - Attach page.on("console", ...) listeners before navigation
        - Attach page.on("pageerror", ...) listeners and assert the array is empty
        - Use page.route() to inspect analytics or audit payloads when relevant
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
        context_chunks: list[SearchResult] = []
        if self.indexer is not None:
            context_chunks = self.indexer.search(description, n_results=self.n_context)

        auth_extra: str | None = None
        if auth_type and auth_type.lower() != "none":
            parts: list[str] = []
            hint = get_auth_hint(auth_type)
            if hint:
                parts.append(hint)
            template = get_template(auth_type)
            if template:
                parts.append("Reference TypeScript template:\n```ts\n" + template + "\n```")
            if parts:
                auth_extra = "\n\n".join(parts)

        combined_extra = extra_context
        if auth_extra and extra_context:
            combined_extra = auth_extra + "\n\n" + extra_context
        elif auth_extra:
            combined_extra = auth_extra

        prompt = self._build_prompt(description, context_chunks, combined_extra)
        result = self.llm_client.complete(prompt)
        if redact_secrets:
            result = self._redact_secrets(result)
        return result

    def plan(self, memory_map_text: str, focus: str | None = None) -> str:
        parts: list[str] = [
            "Below is a memory map of the indexed repository. Use it to propose a comprehensive Playwright test plan.",
            "",
            memory_map_text,
            "",
            "=" * 60,
        ]
        if focus:
            parts += [f"Focus area: {focus}", ""]
        parts += [
            "Generate a Markdown test plan. For each feature area list specific, actionable test scenarios in plain English.",
        ]
        return self.llm_client.complete(
            "\n".join(parts),
            system_prompt=PlaywrightTestGenerator.PLAN_SYSTEM_PROMPT,
        )

    @staticmethod
    def _redact_secrets(code: str) -> str:
        redacted = False

        def _make_replacer(replacement: str) -> Callable[[re.Match[str]], str]:
            def _replace(match: re.Match[str]) -> str:
                nonlocal redacted
                value = match.group(3)
                if _SAFE_VALUES.search(value):
                    return match.group(0)
                redacted = True
                return match.expand(replacement)

            return _replace

        for pattern, replacement in _SECRET_PATTERNS:
            code = pattern.sub(_make_replacer(replacement), code)

        if redacted:
            print(
                "playwright-god: WARNING - hardcoded credentials were detected in the generated output "
                "and replaced with process.env placeholders. Store secrets in environment variables, "
                "never in test code.",
                file=sys.stderr,
            )
        return code

    def _build_prompt(
        self,
        description: str,
        context: Sequence[SearchResult],
        extra_context: str | None,
    ) -> str:
        parts: list[str] = [f"Description: {description}", ""]
        if context:
            parts += ["Context (relevant repository code):", "=" * 60]
            for result in context:
                chunk = result.chunk
                parts += [
                    f"--- {chunk.file_path} (lines {chunk.start_line}-{chunk.end_line}, score={result.score:.3f}) ---",
                    chunk.content,
                    "",
                ]
        if extra_context:
            parts += ["Additional context:", "=" * 60, extra_context, ""]
        parts += [
            "=" * 60,
            "Write a comprehensive TypeScript Playwright test suite for the description above.",
            "Use the context to understand the application structure, user journeys, selectors, and evidence-backed assertions.",
        ]
        return "\n".join(parts)
