import pytest
from playwright.sync_api import Page


@pytest.fixture
def signed_in_user(page: Page):
    """Fixture: signs in a test user via UI or API.

    Replace the body with logic appropriate to the target app (API login or UI flow).
    """
    # TODO: update URL and selectors / API endpoint for the target app
    login_url = "/login"
    page.goto(login_url)
    # Example UI flow - replace selectors
    try:
        page.fill('input[name="email"]', 'test+ci@example.com')
        page.fill('input[name="password"]', 'Password123!')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
    except Exception:
        # If API-based auth is preferred, call the API here and set storage state
        pass
    yield
    # Teardown: sign out if needed
    try:
        page.click('button[aria-label="Sign out"]')
    except Exception:
        pass


@pytest.fixture
def sample_event_payload():
    return {
        "title": "CI Test Event",
        "description": "Automatically created by Playwright test",
        "date": "2099-12-31T20:00:00Z",
        "location": "Test Bar",
    }
