## Context

`playwright-god` currently ends its pipeline at `PlaywrightTestGenerator.generate()` writing a `.spec.ts` file. The user is then expected to set up Playwright themselves and run the spec out-of-band. This boundary is the single biggest barrier to closing the feedback loop the rest of the roadmap depends on (coverage-aware planning, iterative refinement, spec-aware update).

Node/Playwright is the only realistic execution substrate for `@playwright/test` specs — re-implementing the runner in Python is a non-starter. The tool therefore needs a thin, well-typed Python adapter around `npx playwright test`.

## Goals / Non-Goals

**Goals:**
- One-command execution of a generated spec from inside `playwright-god`.
- Structured `RunResult` (Python dataclass) that any downstream feature can consume without re-parsing reporter output.
- Graceful, actionable errors when Node, npm, or `@playwright/test` are missing.
- Preserve raw artifacts (Playwright HTML report, traces, videos) for human inspection.
- Hermetic unit tests (no real Node required) plus one integration test against `tests/fixtures/sample_app/`.

**Non-Goals:**
- Bundling or auto-installing Node/Playwright. The tool detects and instructs.
- Cross-language test runners (pytest, Jest non-Playwright, etc.).
- Browser sandbox troubleshooting on the host (out of scope; documented as a known limitation, mirroring the existing README note).
- Coverage instrumentation — that is the next change (`coverage-aware-planning`).

## Decisions

1. **Subprocess + JSON reporter, not the Node API.** Calling `npx playwright test --reporter=json` keeps the boundary small, matches how Playwright is conventionally driven from CI, and avoids a Node↔Python IPC layer. Trade-off: parsing reporter JSON means we depend on its shape, which is stable but not versioned.
2. **`PlaywrightRunner` is a class, not a free function.** It owns config (working dir, reporter, artifact dir, env passthrough) and exposes `run(spec_path: Path) -> RunResult`. Mirrors the style of `RepositoryIndexer`, `PlaywrightTestGenerator`.
3. **`RunResult` is a frozen dataclass** with: `status` (`passed`/`failed`/`error`), `duration_ms`, `tests: list[TestCaseResult]`, `report_dir: Path | None`, `stdout`, `stderr`, `exit_code`. Each `TestCaseResult` carries `title`, `status`, `duration_ms`, `error_message`, `trace_path`.
4. **Two CLI surfaces:**
   - `playwright-god run <spec-or-dir> [--target-dir DIR] [--reporter json|html|both]` — explicit, useful in CI.
   - `playwright-god generate ... --run` — convenience for the inner loop.
5. **Working directory resolution.** If `--target-dir` is omitted, the runner uses the spec's parent directory walked up to the nearest `package.json`. If none is found, raises `RunnerSetupError` with remediation text.
6. **Detection of prerequisites is upfront and explicit.** `PlaywrightRunner.check_environment()` is called before subprocess; on failure it raises `RunnerSetupError("npx not found on PATH; install Node 18+ and run `npm i -D @playwright/test`")`. This keeps user-visible failures actionable.
7. **Artifacts directory is configurable; default is `<persist-dir>/runs/<timestamp>/`.** Aligns with the existing `.playwright_god_index/` convention.
8. **Secrets passthrough.** The runner forwards `process.env.TEST_USERNAME`, `TEST_PASSWORD`, and any `PLAYWRIGHT_*` vars to the subprocess but never logs them. Consistent with the existing secret-hygiene posture.

## Risks / Trade-offs

- **Reporter JSON shape drift.** Mitigated by pinning the reporter format we parse and adding a regression test fixture (`tests/fixtures/playwright_report_sample.json`).
- **Long test runs block the CLI.** Acceptable for v1; v2 can stream progress. Documented in tasks.
- **Sandbox / browser launch failures on Linux** (already seen in the README's e2e note). Mitigation: the runner surfaces the raw stderr verbatim and links to Playwright's troubleshooting page in the `RunnerSetupError` message; we do not try to fix the host.
- **Subprocess test flake.** Mitigated by mocking `subprocess.run` in unit tests and gating the integration test behind a `pytest.mark.requires_node` marker that auto-skips when `npx` is absent.
- **Cross-platform path handling.** All paths flow through `pathlib.Path`; subprocess invocation uses the list form (no shell). Verified on Linux first; macOS/Windows deferred (documented).
