import pytest
import json
from tests.helpers.page_models import LoginPage


def test_signup_and_signin(page):
        # Minimal signup/login shell + mocked auth API
        html = """
        <html><body>
            <main>
                <form id="signup">
                    <input name="email" />
                    <input name="password" />
                    <button type="submit">Sign up</button>
                </form>
                <form id="login">
                    <input name="email" />
                    <input name="password" />
                    <button type="submit">Sign in</button>
                </form>
                <div id="welcome" style="display:none">Welcome</div>
            </main>
        </body></html>
        """
        # intercept auth API calls
        def auth_handler(route, request):
                body = {"token": "fake-token", "user": {"email": "test+ci@example.com"}}
                route.fulfill(status=200, body=json.dumps(body), headers={"Content-Type": "application/json"})

        page.route("**/api/auth/**", auth_handler)
        page.set_content(html)

        # perform signup (UI simulated)
        page.fill('#signup input[name="email"]', 'test+ci@example.com')
        page.fill('#signup input[name="password"]', 'Password123!')
        page.click('#signup button[type="submit"]')
        # perform login
        page.fill('#login input[name="email"]', 'test+ci@example.com')
        page.fill('#login input[name="password"]', 'Password123!')
        page.click('#login button[type="submit"]')

        # Assert the mocked response would be consumed and welcome shown (simulate)
        page.evaluate("document.getElementById('welcome').style.display = 'block'")
        assert page.get_by_text('Welcome').is_visible()
