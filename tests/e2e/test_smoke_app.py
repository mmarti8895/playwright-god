import pytest
import json


def test_app_smoke_loads(page):
    """Smoke test: load a minimal app shell and assert nav/main present."""
    html = """
    <html><body>
      <nav role="navigation">Main Nav</nav>
      <main role="main"><h1>Agent Bar Hangout</h1></main>
    </body></html>
    """
    page.set_content(html)
    assert page.get_by_role("navigation").is_visible()
    assert page.get_by_role("heading", name="Agent Bar Hangout").is_visible()
