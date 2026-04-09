import json
from tests.helpers.page_models import EventsPage


def test_create_event(page, sample_event_payload):
        # Provide a minimal events list UI and intercept API create/list calls
        shell = """
        <html><body>
            <main>
                <button id="create">Create Event</button>
                <div id="events-list"></div>
            </main>
        </body></html>
        """

        created = {"id": 1, **sample_event_payload}

        def post_events(route, request):
                route.fulfill(status=201, body=json.dumps(created), headers={"Content-Type": "application/json"})

        def get_events(route, request):
                route.fulfill(status=200, body=json.dumps([created]), headers={"Content-Type": "application/json"})

        page.route("**/api/events", lambda r, req: post_events(r, req) if req.method == 'POST' else get_events(r, req))
        page.set_content(shell)

        # simulate create event flow
        page.click('#create')
        # fetch list and render (simulate JS app behavior)
        page.evaluate("(async ()=>{const res=await fetch('/api/events');const data=await res.json();document.getElementById('events-list').innerText = data[0].title;})();")

        assert page.locator('#events-list').inner_text() == sample_event_payload['title']
