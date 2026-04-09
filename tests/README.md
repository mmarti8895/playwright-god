Playwright E2E tests

Quick start

Install dependencies and Playwright browsers:

```bash
python -m pip install -r requirements.txt
playwright install
```

Run full E2E suite:

```bash
pytest tests/e2e -q
```

Notes
- Update fixtures in `tests/fixtures/conftest.py` to match the app's auth and API endpoints.
- Add `data-testid` attributes to critical UI elements to make selectors stable.
