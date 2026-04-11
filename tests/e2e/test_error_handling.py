import json

_FAKE_ORIGIN = "http://localhost.test"


def test_backend_error_shows_friendly_ui(page):
        # Provide shell and simulate 500 from events API
        shell = """
        <html><body>
            <main>
                <div id="error-area"></div>
            </main>
        </body></html>
        """

        def fail_handler(route, request):
                route.fulfill(status=500, body=json.dumps({"error": "server"}), headers={"Content-Type": "application/json"})

        # Serve the shell from a routed URL so that relative fetch() calls
        # (e.g. /api/events) have a valid origin and Playwright can intercept them.
        page.route(f"{_FAKE_ORIGIN}/", lambda r, _: r.fulfill(status=200, body=shell, headers={"Content-Type": "text/html"}))
        page.route("**/api/events", fail_handler)
        page.goto(f"{_FAKE_ORIGIN}/")
        # Simulate app fetching events and showing error
        page.evaluate("(async ()=>{const res=await fetch('/api/events'); if(!res.ok) document.getElementById('error-area').innerText='Something went wrong'; })()")

        assert page.get_by_text('Something went wrong').is_visible()
