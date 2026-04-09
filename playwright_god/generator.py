"""Playwright test generator using LLM + RAG context.

Provides two LLM backends:

* :class:`OpenAIClient` – calls the OpenAI Chat Completions API.
* :class:`TemplateLLMClient` – offline fallback; produces a useful skeleton
  Playwright test from the retrieved context without any API calls.
"""

from __future__ import annotations

import os
import re
import textwrap
from abc import ABC, abstractmethod
from typing import Sequence

from .indexer import RepositoryIndexer, SearchResult


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


class TemplateLLMClient(LLMClient):
    """Offline template-based fallback that does not require an LLM API.

    Generates a syntactically valid Playwright test skeleton based on the
    context chunks retrieved from the repository index.  The generated test
    will need human review but gives a concrete starting point.
    """

    def complete(self, prompt: str) -> str:  # noqa: PLR0914
        """Parse *prompt* and return a template Playwright test."""
        description = self._extract_description(prompt)
        urls = self._extract_urls(prompt)
        selectors = self._extract_selectors(prompt)
        text_content = self._extract_text_content(prompt)
        form_fields = self._extract_form_fields(prompt)

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

        Returns
        -------
        str
            TypeScript Playwright test code.
        """
        context_chunks: list[SearchResult] = []
        if self.indexer is not None:
            context_chunks = self.indexer.search(description, n_results=self.n_context)

        prompt = self._build_prompt(description, context_chunks, extra_context)
        return self.llm_client.complete(prompt)

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
