from playwright.sync_api import expect


def test_layouts_at_common_breakpoints(page):
        html = """
        <html><body>
            <nav>Nav</nav>
            <main><h1>Responsive Test</h1></main>
        </body></html>
        """
        page.set_content(html)
        # mobile
        page.set_viewport_size({"width": 320, "height": 800})
        assert page.get_by_role('heading', name='Responsive Test').is_visible()
        # tablet
        page.set_viewport_size({"width": 768, "height": 1024})
        assert page.get_by_role('heading', name='Responsive Test').is_visible()
        # desktop
        page.set_viewport_size({"width": 1280, "height": 800})
        assert page.get_by_role('heading', name='Responsive Test').is_visible()
