"""Centralized secret patterns and redaction helpers.

Used by both the test generator (to redact secrets out of LLM output) and the
iterative refinement loop (to redact secrets out of failure excerpts before
they are fed back into the next prompt or written to the audit log).
"""

from __future__ import annotations

import re
from typing import Callable

# Replacement patterns used for in-code TypeScript redaction (generator output).
# Each tuple is ``(pattern, replacement)`` where the pattern's group(3) contains
# the captured value to be replaced.
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


# Free-text redaction patterns. These run against arbitrary log/text payloads
# (not TypeScript code). Each pattern matches the secret value and the entire
# match is replaced with ``[REDACTED]`` (or a labelled equivalent that keeps
# the surrounding context readable).
_FREEFORM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer <token>
    (
        re.compile(r"(Authorization\s*:\s*Bearer\s+)([A-Za-z0-9._\-]{8,})", re.IGNORECASE),
        r"\1[REDACTED]",
    ),
    # Generic "Bearer <token>" outside of Authorization headers.
    (
        re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]{16,})"),
        r"\1[REDACTED]",
    ),
    # Provider API keys: sk-..., sk-proj-..., sk_live_..., sk_test_...
    (
        re.compile(r"\bsk-(?:proj-|live_|test_)?[A-Za-z0-9]{16,}\b"),
        "[REDACTED]",
    ),
    # GitHub-style tokens (ghp_, gho_, ghu_, ghs_, ghr_).
    (
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "[REDACTED]",
    ),
    # Google API keys (AIza...).
    (
        re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
        "[REDACTED]",
    ),
    # Anthropic-style keys.
    (
        re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b"),
        "[REDACTED]",
    ),
    # Generic ENV-VAR style assignments: KEY=VALUE where KEY looks secret.
    (
        re.compile(
            r"\b((?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD))"
            r"\s*[=:]\s*['\"]?([^\s'\"]{4,})['\"]?",
        ),
        r"\1=[REDACTED]",
    ),
    # password=... / password: ... in plain text (no quotes).
    (
        re.compile(r"\b(password|passwd|pwd)\s*[=:]\s*([^\s'\";]{4,})", re.IGNORECASE),
        r"\1=[REDACTED]",
    ),
]


def redact(text: str) -> str:
    """Return ``text`` with any secret-looking substrings replaced.

    This is intended for free-form text (failure logs, tracebacks, env dumps)
    that may flow into LLM prompts or the refinement audit log. It is *not*
    a substitute for the TypeScript-aware redactor in
    :func:`playwright_god.generator.PlaywrightTestGenerator._redact_secrets`,
    which handles generator output.

    Idempotent: ``redact(redact(x)) == redact(x)``.
    """

    if not text:
        return text
    out = text
    for pattern, replacement in _FREEFORM_PATTERNS:
        out = pattern.sub(replacement, out)
    return out


def make_code_replacer(
    replacement: str, *, on_replace: Callable[[], None] | None = None
):
    """Return a regex sub callback for the TypeScript-code patterns.

    Used by the generator's output redactor. The callback respects
    ``_SAFE_VALUES`` (so already-safe placeholders such as ``process.env.X``
    are not rewritten) and invokes ``on_replace`` once per substitution.
    """

    def _replace(match: "re.Match[str]") -> str:
        value = match.group(3)
        if _SAFE_VALUES.search(value):
            return match.group(0)
        if on_replace is not None:
            on_replace()
        return match.expand(replacement)

    return _replace


__all__ = [
    "_SECRET_PATTERNS",
    "_SAFE_VALUES",
    "_FREEFORM_PATTERNS",
    "redact",
    "make_code_replacer",
]
