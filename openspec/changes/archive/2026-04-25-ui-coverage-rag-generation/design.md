## Context

The desktop app already has section components for Coverage & Gaps (`CoverageView`), RAG Search (`RagView`), and Generation (`Generation`). However, these sections rely on asynchronous artifact reads, pipeline run state, and cross-section store handoffs that can drift out of sync when repository context or run status changes.

The existing architecture intentionally keeps orchestration in the CLI and treats the desktop app as a shell. This design keeps that boundary: UI reliability improvements are implemented through deterministic state transitions and stronger artifact lifecycle handling, not by duplicating pipeline logic in the frontend.

## Goals / Non-Goals

**Goals:**
- Make Coverage & Gaps, RAG Search, and Generation usable as a reliable end-to-end loop in one desktop session.
- Ensure Coverage-to-Generation handoff always pre-fills the intended prompt and opens the correct section.
- Standardize loading, empty, and error states for coverage and search artifacts against the active repository.
- Ensure artifact-driven sections refresh after relevant runs complete.
- Add tests that lock in these behaviors.

**Non-Goals:**
- Re-architect the pipeline engine or move orchestration from CLI to desktop.
- Add new artifact types or change the underlying `.pg_runs` format.
- Introduce new backend services or non-local storage.

## Decisions

### Decision: Keep a single source of truth in UI stores for cross-section intent
Coverage-triggered generation uses `useUIStore` prompt handoff (`setGenerationPrompt`) and section switch (`setActiveSection`). This remains the integration path, with stricter consume-once behavior in Generation.

Alternatives considered:
- Pass prompt via URL-like route params in a client router. Rejected because the app uses store-based section state, not route URLs.
- Use transient component-level state only. Rejected because handoff crosses section boundaries.

### Decision: Normalize artifact read lifecycle per section
Coverage and RAG sections use a common pattern: clear stale state when repo changes, load asynchronously, and render one of loading/empty/error/content states from explicit state values.

Alternatives considered:
- Opportunistic rendering with partial null checks. Rejected because it causes inconsistent empty states and stale data flashes.
- Centralized query framework adoption. Rejected for scope; a local lifecycle cleanup is sufficient.

### Decision: Tie post-run refresh to existing artifact version signaling
Artifact viewers refresh by listening to the existing artifact version signal in UI state after pipeline events. This avoids polling and preserves the current event-driven architecture.

Alternatives considered:
- Poll `.pg_runs` on interval. Rejected due to unnecessary IO and lag.
- Force manual refresh controls only. Rejected as poorer UX for frequent generation iterations.

### Decision: Keep generation execution path through managed pipeline runner
Generation continues to call the managed pipeline entrypoint (`runManagedPipeline`) with a mode/description and uses pipeline store status for progress/cancel/error.

Alternatives considered:
- Add a second ad-hoc command path for generation. Rejected because dual paths increase divergence and test surface.

## Risks / Trade-offs

- [Risk] Stricter state resets can hide in-flight results if repo context changes quickly. -> Mitigation: gate updates on active repo and cancellation flags, and test repo-switch behavior.
- [Risk] Prompt handoff could be consumed unexpectedly during concurrent updates. -> Mitigation: keep consume-and-clear semantics in one effect and cover with section integration tests.
- [Risk] Viewer refresh coupling to artifact version assumes all relevant runs emit updates. -> Mitigation: add tests around run completion events and fallback manual navigation refresh behavior.

## Migration Plan

1. Update section state/loader behavior in Coverage, RAG, and Generation components.
2. Update artifact/pipeline utility functions only where needed to support deterministic UI state and refresh signaling.
3. Add or update tests for:
   - Coverage table/gaps rendering and generate action handoff
   - RAG missing-index/indexing/ready/search states
   - Generation prompt prefill + run/cancel status transitions
4. Validate with desktop test suite and targeted manual smoke through section workflow.

Rollback strategy:
- Revert the UI/state updates in the affected section and utility files; no data migration is required because artifact formats remain unchanged.

## Open Questions

- Should Generation expose a distinct "generate-only" run mode in the primary button label, or keep "Run Pipeline" wording while passing description context?
- Should RAG keep a fixed default top-N of 10 or remember the last user selection per repository?