"""Playwright test generator using LLM + RAG context."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest.mock
from abc import ABC, abstractmethod
from typing import Callable, Sequence

from ._secrets import _SAFE_VALUES, _SECRET_PATTERNS  # re-exported for back-compat
from .auth_templates import get_auth_hint, get_template
from .indexer import RepositoryIndexer, SearchResult


class LLMClient(ABC):
    """Abstract base class for LLM completion backends."""

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Send *prompt* to the LLM and return its text response."""


class OpenAIClient(LLMClient):
    """Calls the OpenAI Chat Completions API."""

    _RETRYABLE_ERROR_NAMES = ("APIConnectionError", "APITimeoutError")
    _MAX_ATTEMPTS = 2
    _RETRY_DELAY_SECONDS = 0.5

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o") -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIClient. Install it with: pip install openai"
            ) from exc

        import openai

        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))
        self.model = model

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        sys_msg = system_prompt or PlaywrightTestGenerator.SYSTEM_PROMPT
        last_error: Exception | None = None
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                if not self._is_retryable_error(exc) or attempt >= self._MAX_ATTEMPTS:
                    raise
                last_error = exc
                time.sleep(self._RETRY_DELAY_SECONDS)
        if last_error is not None:
            raise last_error
        return ""

    def _is_retryable_error(self, exc: Exception) -> bool:
        return exc.__class__.__name__ in self._RETRYABLE_ERROR_NAMES


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


class PlaywrightCLIError(RuntimeError):
    """Raised when the ``playwright-cli`` backend fails to produce a spec.

    Always carries an actionable remediation message.
    """


class PlaywrightCLIClient(LLMClient):
    """Drives ``npx playwright codegen`` to capture a browser-recorded TypeScript spec.

    When invoked, it runs ``npx playwright codegen --output <tmp_file> <url>``
    and blocks until the Playwright Inspector window is closed (or the optional
    *timeout* is exceeded).  The recorded TypeScript code is returned as the
    completion result.

    If no URL can be resolved (neither an explicit *url* nor one extracted from
    the prompt), the client transparently falls back to
    :class:`TemplateLLMClient`.

    The memory-map / RAG context injected by :class:`PlaywrightTestGenerator`
    is still assembled in full and passed as *prompt*.  This client uses that
    context to locate the target URL; the recorded browser interactions then
    replace the LLM completion step.

    Parameters
    ----------
    executable:
        Path or name of the ``npx`` binary.  Defaults to ``"npx"`` so that
        whatever ``npx`` is on ``PATH`` is used.
    timeout:
        Seconds to wait for the user to finish recording before killing the
        browser and raising :class:`PlaywrightCLIError`.  Defaults to 300 s
        (5 minutes).
    url:
        Optional explicit base URL passed to ``playwright codegen``.  When
        provided, it overrides any URL found in the prompt.
    """

    DEFAULT_TIMEOUT: int = 300

    def __init__(
        self,
        executable: str = "npx",
        timeout: int = DEFAULT_TIMEOUT,
        url: str | None = None,
    ) -> None:
        self.executable = executable
        timeout = int(timeout)
        if timeout < 1:
            raise PlaywrightCLIError(
                "Invalid Playwright CLI timeout: expected an integer >= 1 second. "
                "Use --playwright-cli-timeout with a positive value."
            )
        self.timeout = timeout
        self.url = url
        self._fallback = TemplateLLMClient()

    def complete(self, prompt: str, system_prompt: str | None = None) -> str:  # noqa: ARG002
        """Run ``playwright codegen`` and return the recorded TypeScript spec.

        The *system_prompt* parameter is accepted for interface compatibility
        with other ``LLMClient`` backends but is intentionally unused here —
        ``npx playwright codegen`` does not accept a system prompt; it records
        actual browser interactions instead.

        Falls back to :class:`TemplateLLMClient` when no URL is available or
        when codegen exits cleanly but writes no output.

        Raises
        ------
        PlaywrightCLIError
            When the executable is not found, the process times out, or
            codegen exits with a non-zero code alongside empty output.
        """
        if shutil.which(self.executable) is None:
            raise PlaywrightCLIError(
                f"{self.executable!r} not found on PATH. "
                "Install Node.js 18+ (https://nodejs.org) so that npx is available, "
                "then run `npx playwright install` to install Playwright browsers."
            )

        # Resolve the target URL: explicit override > first URL found in prompt.
        url = self.url
        if url is None:
            found = re.findall(r"https?://[^\s\"'<>]+", prompt)
            url = found[0] if found else None

        if url is None:
            # No URL available — fall back to the offline template generator.
            return self._fallback.complete(prompt)

        # Create a temp file for the generated spec; playwright codegen overwrites it.
        fd, tmp_path = tempfile.mkstemp(suffix=".spec.ts", prefix="pg_codegen_")
        os.close(fd)

        try:
            proc = subprocess.Popen(
                [self.executable, "playwright", "codegen", "--output", tmp_path, url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                _stdout, stderr = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise PlaywrightCLIError(
                    f"playwright codegen timed out after {self.timeout}s against {url!r}. "
                    "Close the Playwright Inspector window before the timeout or increase "
                    "--playwright-cli-timeout."
                )

            try:
                with open(tmp_path, "r", encoding="utf-8") as fh:
                    code = fh.read()
            except OSError:
                code = ""

            if not code.strip():
                if proc.returncode != 0:
                    raise PlaywrightCLIError(
                        f"playwright codegen exited with code {proc.returncode} "
                        f"for {url!r}. "
                        f"stderr: {stderr[:500] if stderr else '(none)'}"
                    )
                # Codegen ran but wrote nothing (e.g. user dismissed without recording).
                return self._fallback.complete(prompt)

            return code

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


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
        uncovered_excerpts: Sequence[tuple[str, int, int, str]] | None = None,
        uncovered_cap: int = 12,
        failure_excerpt: str | None = None,
        coverage_delta: "object | None" = None,
        flow_graph: "object | None" = None,
        flow_graph_cap: int = 5,
        seed_spec_content: str | None = None,
        generation_mode: str = "static",
        repo_profile: "object | None" = None,
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

        if uncovered_excerpts:
            gap_block = self._format_uncovered_block(
                uncovered_excerpts, cap=uncovered_cap
            )
            if gap_block:
                combined_extra = (
                    (combined_extra + "\n\n" + gap_block) if combined_extra else gap_block
                )

        if failure_excerpt:
            failure_block = self._format_failure_excerpt(failure_excerpt)
            if failure_block:
                combined_extra = (
                    (combined_extra + "\n\n" + failure_block)
                    if combined_extra
                    else failure_block
                )

        if coverage_delta:
            delta_block = self._format_coverage_delta_addendum(coverage_delta)
            if delta_block:
                combined_extra = (
                    (combined_extra + "\n\n" + delta_block)
                    if combined_extra
                    else delta_block
                )

        if flow_graph is not None:
            graph_block = self._format_flow_graph_subgraph(
                flow_graph, description, cap=flow_graph_cap
            )
            if graph_block:
                combined_extra = (
                    (combined_extra + "\n\n" + graph_block)
                    if combined_extra
                    else graph_block
                )

        if seed_spec_content is not None:
            seed_block = self._format_seed_spec(seed_spec_content)
            if seed_block:
                combined_extra = (
                    (combined_extra + "\n\n" + seed_block)
                    if combined_extra
                    else seed_block
                )

        mode_block = self._format_generation_mode(generation_mode, repo_profile=repo_profile)
        if mode_block:
            combined_extra = (
                (combined_extra + "\n\n" + mode_block)
                if combined_extra
                else mode_block
            )

        prompt = self._build_prompt(description, context_chunks, combined_extra)
        result = self.llm_client.complete(prompt)
        if redact_secrets:
            result = self._redact_secrets(result)
        # Skip provenance banner for the offline template client and for mocked
        # LLM clients used by tests, which expect raw outputs byte-for-byte.
        if not isinstance(self.llm_client, (TemplateLLMClient, unittest.mock.NonCallableMock)):
            result = self._add_provenance_banner(
                result,
                generation_mode=generation_mode,
                repo_profile=repo_profile,
            )
        return result

    def plan(
        self,
        memory_map_text: str,
        focus: str | None = None,
        *,
        coverage: dict | None = None,
        prioritize: str = "absolute",
        flow_graph: "object | None" = None,
    ) -> str:
        parts: list[str] = [
            "Below is a memory map of the indexed repository. Use it to propose a comprehensive Playwright test plan.",
            "",
            memory_map_text,
            "",
            "=" * 60,
        ]
        if focus:
            parts += [f"Focus area: {focus}", ""]

        if coverage:
            delta = self._format_coverage_delta(
                coverage, prioritize=prioritize, flow_graph=flow_graph
            )
            if delta:
                parts += [delta, ""]

        if flow_graph is not None:
            graph_summary = self._format_flow_graph_for_plan(
                flow_graph, coverage=coverage
            )
            if graph_summary:
                parts += [graph_summary, ""]

        parts += [
            "Generate a Markdown test plan. For each feature area list specific, actionable test scenarios in plain English.",
        ]
        if coverage:
            parts += [
                "Include a `## Coverage Delta` section that lists the highest-priority "
                "uncovered files and the scenarios that would close those gaps.",
            ]
        if flow_graph is not None:
            parts += [
                "When a flow graph is supplied, annotate each feature area with the "
                "uncovered routes and actions it should target.",
            ]
        return self.llm_client.complete(
            "\n".join(parts),
            system_prompt=PlaywrightTestGenerator.PLAN_SYSTEM_PROMPT,
        )

    @staticmethod
    def _format_coverage_delta(
        coverage: dict,
        *,
        prioritize: str = "absolute",
        flow_graph: "object | None" = None,
    ) -> str:
        """Format a `Coverage Delta` block listing prioritised uncovered files."""

        files = coverage.get("files") or []
        if not files:
            return ""

        # When prioritising by routes, order files by how many uncovered routes
        # cite them as handler evidence.
        route_weight: dict[str, int] = {}
        if prioritize == "routes" and flow_graph is not None:
            uncovered_route_ids: set[str] = set()
            cov_routes = (coverage.get("routes") or {}) if isinstance(coverage, dict) else {}
            if isinstance(cov_routes, dict):
                uncovered_route_ids = set(cov_routes.get("uncovered") or [])
            for route in getattr(flow_graph, "routes", ()) or ():
                if uncovered_route_ids and route.id not in uncovered_route_ids:
                    continue
                for ev in getattr(route, "evidence", ()) or ():
                    f = getattr(ev, "file", None)
                    if f:
                        route_weight[f] = route_weight.get(f, 0) + 1

        def _key(entry: dict):
            uncovered = len(entry.get("uncovered_lines") or [])
            percent = float(entry.get("percent", 100.0))
            if prioritize == "percent":
                return (percent, -uncovered)
            if prioritize == "routes":
                # Highest route-weight first (most uncovered routes touching this file).
                return (-route_weight.get(entry.get("path", ""), 0), -uncovered, percent)
            return (-uncovered, percent)

        ranked = sorted(
            (e for e in files if isinstance(e, dict) and e.get("uncovered_lines")),
            key=_key,
        )
        if not ranked:
            return ""

        summary = coverage.get("summary") or {}
        lines: list[str] = ["## Coverage Delta"]
        if summary:
            lines.append(
                f"Overall: {summary.get('percent', 0.0)}% covered "
                f"({summary.get('covered_lines', 0)}/"
                f"{summary.get('covered_lines', 0) + summary.get('uncovered_lines', 0)} lines, "
                f"{summary.get('files', 0)} files)."
            )
        lines.append("")
        lines.append(f"Prioritised by: {prioritize}")
        lines.append("")
        for entry in ranked[:12]:
            uncovered = entry.get("uncovered_lines") or []
            extra = ""
            if prioritize == "routes":
                w = route_weight.get(entry.get("path", ""), 0)
                if w:
                    extra = f", {w} uncovered route(s)"
            lines.append(
                f"- `{entry.get('path', '?')}` — {entry.get('percent', 0.0)}% "
                f"covered, {len(uncovered)} uncovered line(s){extra}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_flow_graph_for_plan(
        flow_graph: "object | None",
        *,
        coverage: dict | None = None,
    ) -> str:
        """Annotate the plan prompt with a flow-graph summary.

        When *coverage* contains a ``routes`` block, uncovered routes are
        called out explicitly so the planner can drive scenarios at them.
        """

        if flow_graph is None:
            return ""
        routes = tuple(getattr(flow_graph, "routes", ()) or ())
        actions = tuple(getattr(flow_graph, "actions", ()) or ())
        if not routes and not actions:
            return ""
        uncovered_ids: set[str] = set()
        has_routes_block = False
        if isinstance(coverage, dict):
            cov_routes = coverage.get("routes") or {}
            if isinstance(cov_routes, dict) and "uncovered" in cov_routes:
                has_routes_block = True
                uncovered_ids = set(cov_routes.get("uncovered") or [])
        lines = ["## Flow Graph"]
        if routes:
            lines.append(f"Routes: {len(routes)}")
            shown = 0
            for r in routes:
                if has_routes_block and r.id not in uncovered_ids:
                    continue
                lines.append(f"- uncovered: `{r.id}`")
                shown += 1
                if shown >= 12:
                    break
            if has_routes_block and shown == 0:
                lines.append("- (all routes covered)")
        if actions:
            lines.append("")
            lines.append(f"Actions: {len(actions)} (sample of 8)")
            for a in actions[:8]:
                lines.append(f"- `{a.id}`")
        return "\n".join(lines)

    @staticmethod
    def _format_generation_mode(
        generation_mode: str,
        *,
        repo_profile: "object | None" = None,
    ) -> str:
        mode = (generation_mode or "static").strip().lower()
        guidance = {
            "static": "Bias toward repository evidence, named routes, and stable selectors already visible in source.",
            "runtime": "Bias toward browser-observable flows, resilient user-facing locators, and navigable journeys.",
            "hybrid": "Fuse static repository evidence with runtime-observable user journeys. Prefer high-confidence smoke coverage first.",
            "repair": "Preserve existing intent where possible, but repair selectors, waits, and assertions that are likely brittle.",
            "gap-fill": "Prioritize uncovered routes, journeys, and edge cases that appear missing from the current suite.",
        }.get(mode, "Prefer the most evidence-backed Playwright coverage available.")
        lines = [
            "Generation mode",
            "---------------",
            f"Mode: {mode}",
            guidance,
        ]
        if repo_profile is not None and hasattr(repo_profile, "archetype"):
            lines.append(
                f"Repository archetype: {getattr(repo_profile, 'archetype', 'unknown')} "
                f"(confidence={getattr(repo_profile, 'confidence', 0.0):.2f})"
            )
            frameworks = getattr(repo_profile, "frameworks", ()) or ()
            if frameworks:
                lines.append("Frameworks: " + ", ".join(str(item) for item in frameworks[:6]))
        return "\n".join(lines)

    @staticmethod
    def _add_provenance_banner(
        result: str,
        *,
        generation_mode: str,
        repo_profile: "object | None" = None,
    ) -> str:
        if not result.strip():
            return result
        if result.lstrip().startswith("// Generated by playwright-god"):
            return result
        confidence = None
        archetype = None
        if repo_profile is not None:
            confidence = getattr(repo_profile, "confidence", None)
            archetype = getattr(repo_profile, "archetype", None)
        meta = f"mode={generation_mode}"
        if archetype:
            meta += f", archetype={archetype}"
        if confidence is not None:
            meta += f", confidence={float(confidence):.2f}"
        banner = f"// Generated by playwright-god ({meta})\n"
        return banner + result

    @staticmethod
    def _format_flow_graph_subgraph(
        flow_graph: "object",
        description: str,
        *,
        cap: int = 5,
    ) -> str:
        """Return a `Relevant routes & actions` block for a generate prompt.

        Heuristic: rank routes/actions by simple keyword overlap with the
        description, then take the top *cap* of each.
        """

        routes = tuple(getattr(flow_graph, "routes", ()) or ())
        actions = tuple(getattr(flow_graph, "actions", ()) or ())
        if not routes and not actions:
            return ""
        terms = {t.lower() for t in re.findall(r"[A-Za-z]{3,}", description or "")}

        def _score(node_id: str, *extra: str) -> int:
            blob = " ".join((node_id, *extra)).lower()
            return sum(1 for t in terms if t in blob)

        ranked_routes = sorted(
            routes,
            key=lambda r: (-_score(r.id, r.path, r.handler), r.id),
        )[:max(0, int(cap))]
        ranked_actions = sorted(
            actions,
            key=lambda a: (-_score(a.id, a.role, a.file), a.id),
        )[:max(0, int(cap))]
        if not ranked_routes and not ranked_actions:
            return ""

        lines = ["Relevant routes & actions:", "=" * 60]
        if ranked_routes:
            lines.append("Routes:")
            for r in ranked_routes:
                ev = ""
                if r.evidence:
                    e0 = r.evidence[0]
                    ev = f" ({e0.file}:{e0.line_range[0]}-{e0.line_range[1]})"
                lines.append(f"  - {r.id}{ev}")
        if ranked_actions:
            lines.append("Actions:")
            for a in ranked_actions:
                ev = ""
                if a.evidence:
                    e0 = a.evidence[0]
                    ev = f" ({e0.file}:{e0.line_range[0]}-{e0.line_range[1]})"
                lines.append(f"  - {a.id}{ev}")
        return "\n".join(lines)

    @staticmethod
    def _format_uncovered_block(
        excerpts: Sequence[tuple[str, int, int, str]],
        *,
        cap: int = 12,
    ) -> str:
        """Format an `Uncovered code (gaps)` block to inject into a generate prompt.

        Each excerpt is ``(file_path, start_line, end_line, source_text)``.
        Capped at ``cap`` entries.
        """

        if not excerpts:
            return ""
        head = excerpts[: max(0, int(cap))]
        if not head:
            return ""
        lines: list[str] = ["Uncovered code (gaps):", "=" * 60]
        for path, start, end, body in head:
            lines.append(f"--- {path} (lines {start}-{end}) ---")
            lines.append(body.rstrip())
            lines.append("")
        if len(excerpts) > len(head):
            lines.append(
                f"(+{len(excerpts) - len(head)} more uncovered excerpts omitted)"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_failure_excerpt(excerpt: str, *, max_bytes: int = 1800) -> str:
        """Format a `Previous attempt failure` block.

        The excerpt is expected to have already been redacted by the caller
        (the refinement loop runs it through :func:`playwright_god._secrets.redact`
        before invoking ``generate``). We do *not* re-redact here so that the
        caller's choice is honoured byte-for-byte.
        """

        if not excerpt or not excerpt.strip():
            return ""
        body = excerpt
        if len(body.encode("utf-8")) > max_bytes:
            body = body.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
            body = body.rstrip() + "\n... (truncated)"
        return "Previous attempt failure:\n" + ("=" * 60) + "\n" + body.rstrip()

    @staticmethod
    def _format_coverage_delta_addendum(delta: object) -> str:
        """Format a `Coverage delta since last attempt` block.

        ``delta`` may be:
        - a mapping with ``newly_covered`` / ``still_uncovered`` lists, or
        - any object exposing those attributes (e.g. a dataclass), or
        - an iterable of ``(path, status)`` pairs.
        """

        if delta is None:
            return ""

        newly_covered: list[str] = []
        still_uncovered: list[str] = []

        if isinstance(delta, dict):
            newly_covered = list(delta.get("newly_covered") or [])
            still_uncovered = list(delta.get("still_uncovered") or [])
        else:
            newly_covered = list(getattr(delta, "newly_covered", []) or [])
            still_uncovered = list(getattr(delta, "still_uncovered", []) or [])

        if not newly_covered and not still_uncovered:
            return ""

        lines = ["Coverage delta since last attempt:", "=" * 60]
        if newly_covered:
            lines.append("Newly covered:")
            for path in newly_covered[:20]:
                lines.append(f"  + {path}")
        if still_uncovered:
            lines.append("Still uncovered:")
            for path in still_uncovered[:20]:
                lines.append(f"  - {path}")
        return "\n".join(lines)

    @staticmethod
    def _format_seed_spec(content: str, *, max_bytes: int = 8192) -> str:
        """Format a `Current spec to refine` block for seed-based refinement.

        When updating an existing spec, this block provides the current spec's
        content so the LLM can refine it rather than generating from scratch.
        """

        if not content or not content.strip():
            return ""
        body = content
        if len(body.encode("utf-8")) > max_bytes:
            body = body.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
            body = body.rstrip() + "\n// ... (truncated)"
        return (
            "Current spec to refine:\n"
            + ("=" * 60)
            + "\n```typescript\n"
            + body.rstrip()
            + "\n```\n"
            + ("=" * 60)
            + "\n\nRefine and improve this existing spec based on the description above. "
            "Preserve working parts and fix or enhance as needed."
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
