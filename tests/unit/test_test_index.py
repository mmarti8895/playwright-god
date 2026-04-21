from __future__ import annotations

from pathlib import Path

from playwright_god.test_index import TestIndex, infer_test_journeys


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_indexes_multiple_frameworks(tmp_path: Path):
    _write(
        tmp_path / "tests" / "login.spec.ts",
        'import { test, expect } from "@playwright/test";\n'
        'test("login", async ({ page }) => { await page.goto("/login"); await expect(page).toHaveURL(/login/); });\n',
    )
    _write(
        tmp_path / "cypress" / "e2e" / "home.cy.ts",
        'describe("home", () => { it("works", () => { cy.visit("/"); cy.contains("Home"); }); });\n',
    )
    index = TestIndex.build(tmp_path)
    assert len(index) == 2
    assert index.get("tests/login.spec.ts").owner_framework == "playwright"
    assert index.get("cypress/e2e/home.cy.ts").owner_framework == "cypress"


def test_duplicates_for_matches_by_nodes_and_journeys(tmp_path: Path):
    _write(
        tmp_path / "tests" / "login.spec.ts",
        '// @pg-tags route:GET:/login\n'
        'import { test } from "@playwright/test";\n'
        'test("login", async ({ page }) => { await page.goto("/login"); });\n',
    )
    index = TestIndex.build(tmp_path)
    matches = index.duplicates_for(
        covered_nodes=("route:GET:/login",),
        covered_journeys=("visit:/login",),
    )
    assert matches == ["tests/login.spec.ts"]


def test_infer_test_journeys_extracts_visits_and_assertions():
    journeys = infer_test_journeys(
        'await page.goto("/settings"); await expect(page.getByText("Settings")).toBeVisible();'
    )
    assert "visit:/settings" in journeys
    assert any(item.startswith("assert:") for item in journeys)
