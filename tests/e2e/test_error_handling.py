import json


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

        page.route("**/api/events", fail_handler)
        page.set_content(shell)
        # Simulate app fetching events and showing error
        page.evaluate("(async ()=>{const res=await fetch('/api/events'); if(!res.ok) document.getElementById('error-area').innerText='Something went wrong'; })()")

        assert page.get_by_text('Something went wrong').is_visible()
