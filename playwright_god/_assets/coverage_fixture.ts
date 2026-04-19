/**
 * playwright-god JS coverage fixture.
 *
 * Wraps Playwright's `test` so that every test starts/stops Chromium's V8
 * coverage and writes the raw payload to a file the runner can pick up.
 *
 * Usage in a generated spec:
 *
 *     import { test, expect } from "playwright-god/coverage_fixture";
 *
 * Or registered via `playwright.config.ts` so it applies to every spec.
 *
 * Output file: `<PLAYWRIGHT_GOD_COVERAGE_DIR>/<test-id>.coverage.json`
 *
 * Limitations:
 *   - Only works under Chromium. The fixture detects the browser at setup
 *     and silently no-ops on Firefox / WebKit. The Python collector emits a
 *     structured warning in that case.
 */

import { test as base, expect, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

type CoverageEntry = {
    url: string;
    source?: string;
    functions?: Array<{
        ranges: Array<{ startOffset: number; endOffset: number; count: number }>;
    }>;
};

type Fixtures = {
    coveragePage: Page;
};

const OUTPUT_DIR =
    process.env.PLAYWRIGHT_GOD_COVERAGE_DIR ?? join(process.cwd(), ".pg_coverage");

export const test = base.extend<Fixtures>({
    coveragePage: async ({ page, browserName }, use, testInfo) => {
        const supported = browserName === "chromium";
        if (supported) {
            await page.coverage.startJSCoverage({ resetOnNavigation: false });
        }
        await use(page);
        if (!supported) {
            return;
        }
        const data: CoverageEntry[] = await page.coverage.stopJSCoverage();
        try {
            mkdirSync(OUTPUT_DIR, { recursive: true });
            const safeId = testInfo.testId.replace(/[^a-zA-Z0-9_-]/g, "_");
            writeFileSync(
                join(OUTPUT_DIR, `${safeId}.coverage.json`),
                JSON.stringify(data),
                "utf-8",
            );
        } catch (err) {
            // Best-effort — never fail a test because coverage couldn't be saved.
            // eslint-disable-next-line no-console
            console.warn(`[playwright-god] could not write coverage: ${err}`);
        }
    },
});

export { expect };
