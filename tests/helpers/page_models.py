from playwright.sync_api import Page


class LandingPage:
    def __init__(self, page: Page):
        self.page = page

    def goto(self):
        self.page.goto("/")

    def has_nav(self):
        return self.page.get_by_role("navigation").is_visible()


class LoginPage:
    def __init__(self, page: Page):
        self.page = page

    def login(self, email: str, password: str):
        self.page.fill('input[name="email"]', email)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state('networkidle')


class EventsPage:
    def __init__(self, page: Page):
        self.page = page

    def goto(self):
        self.page.goto("/events")

    def create_event(self, payload: dict):
        # Replace with real flow
        self.page.click('button:has-text("Create Event")')
        self.page.fill('input[name="title"]', payload.get('title', ''))
        self.page.fill('textarea[name="description"]', payload.get('description', ''))
        self.page.click('button:has-text("Save")')
        self.page.wait_for_load_state('networkidle')
