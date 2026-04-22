# Desktop manual-QA checklist

Run this checklist before publishing a `desktop-v*` release tag. The automated
suites (`vitest`, `cargo test --lib`, `npm run lint`, `npm run build`) cover the
unit/integration layer but the items below need a human at a real window.

## Environments

- **macOS** (Apple Silicon, latest stable Tauri 2 toolchain, Node 20, Rust stable)
- **Linux** (Ubuntu 22.04 / Fedora 40 — both x86_64 and Wayland/X11 if available)

> Windows is intentionally out of scope for this change; do not test there.

## 1. Window chrome

- [ ] macOS: titlebar uses `hiddenInset`, traffic lights are visible, the
      sidebar shows the **vibrancy** material (translucent, picks up desktop
      tint when the window is active and slightly muted when inactive).
- [ ] Linux: vibrancy is **not** attempted (no console errors). The sidebar
      renders an opaque `--surface-1` fallback color.
- [ ] Window remembers its position/size across restarts.
- [ ] Drag region: clicking the empty space along the top of the sidebar
      drags the window; clicking buttons does not.

## 2. Repository selection

- [ ] Selecting a repo updates the title bar and persists in **Recent**.
- [ ] Recent list keeps at most 10 entries, MRU first; clearing one removes it.
- [ ] Selecting a non-existent or non-readable path surfaces a toast error and
      does not update Recent.

## 3. Pipeline run (against a real `.pg_runs/` directory)

Pick a repo where `playwright-god index` + `generate` + `inspect` have already
been run at least once so the artifact viewers have something to show.

- [ ] **Run pipeline** streams stdout/stderr lines into the OutputPane in
      real time, with monotonic ordering.
- [ ] Cancel button stops the subprocess (verify with `ps`/Activity Monitor)
      and the UI returns to idle within ~1s.
- [ ] On success, the run appears in the Audit log with the correct
      command, exit code, duration, and `run_id`.

## 4. Artifact viewers

For each viewer, open the most recent run and confirm the data renders
without errors and that empty-state messaging is sensible when the
artifact is missing.

- [ ] **Memory map** — file tree and chunk preview both populated.
- [ ] **Flow graph** — reactflow canvas pans/zooms; nodes selectable.
- [ ] **Coverage** — Files tab defaults to least-covered first; clicking the
      `%` and `Path` headers toggles sort. Routes tab also sorts. The CSV
      export writes a file at the path chosen in the save dialog and a
      "Saved to …" toast appears.
- [ ] **RAG context** — chunk list scrolls smoothly with virtualization
      (try a 5k-chunk repo); chunk preview shows source + score.
- [ ] **Audit log** — filters (status, command, date) compose; CSV export
      produces a parseable file.
- [ ] **Codegen stream** — toggle the live-tail checkbox; LLM transcripts
      and codegen output appear in their respective panes; unchecking
      stops new lines and clears buffered events.
- [ ] **Inspect / Discover** — collapsible sections expand; the
      "Preview Prompt" form renders the assembled prompt in the
      read-only pane.

## 5. Settings & secrets

- [ ] Changing the CLI path to an invalid value shows the validation error
      and disables Save.
- [ ] **Detect CLI** finds `playwright-god` on `PATH`.
- [ ] Saving an API key writes it to the OS keychain on macOS / Secret
      Service on Linux. With both unavailable, the fallback JSON file is
      created with `0600` permissions (verify with `ls -l`).
- [ ] Removing a key clears it from both the keychain and the fallback file.

## 6. Accessibility

- [ ] Tab through every section: focus outlines (2px ink-900, 2px offset)
      are visible on every interactive element.
- [ ] `aria-current="page"` set on the active sidebar item; nav has
      `aria-label="Primary"`.
- [ ] All Radix primitives (Dialog, Checkbox, Select, Toast) trap focus
      correctly and dismiss on `Esc`.
- [ ] Screen-reader smoke test (VoiceOver on macOS, Orca on Linux): the
      sidebar is announced as a navigation landmark and each section
      heading is reachable via heading navigation.

## 7. Release artifacts (after `npm run tauri build`)

- [ ] macOS `.dmg` mounts, the app launches, and Gatekeeper warning is
      the only friction (signing/notarization is out of scope for the
      experimental release).
- [ ] Linux `.AppImage` is executable (`chmod +x`) and launches on a
      vanilla Ubuntu 22.04 with the documented apt deps installed.
- [ ] Both bundles open the previously-tested repo and reproduce the
      viewer behavior from sections 3–4.

## Sign-off

Record the QA pass in the release notes:

```text
QA: <yyyy-mm-dd>
- macOS <version> on <hardware>: PASS / FAIL (notes)
- Linux <distro> <version>:      PASS / FAIL (notes)
```
