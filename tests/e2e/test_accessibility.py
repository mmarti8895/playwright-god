import pytest


def test_basic_accessibility(page):
        # Minimal page to check ARIA landmarks
        html = """
        <html><body>
            <header role="banner">Site header</header>
            <main role="main">Content</main>
        </body></html>
        """
        page.set_content(html)
        assert page.get_by_role('main').is_visible()
        assert page.get_by_role('banner').is_visible()
