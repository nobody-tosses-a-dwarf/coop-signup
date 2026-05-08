"""
End-to-end browser tests using Playwright.

These open a real Chromium browser and walk through the site exactly like
a human would — typing in fields, clicking buttons, etc. Catches things
unit tests can't (broken CSS, missing buttons, JavaScript errors).

Before running:
  1. Start the dev server in another terminal (leave it running):
       python -m uvicorn app:app --reload --port 8000
  2. Then run these tests:
       python -m pytest test_e2e.py --headed      # watch the browser do it
       python -m pytest test_e2e.py               # invisible (faster, for CI)

If the browser moves too fast to follow, slow it down:
       python -m pytest test_e2e.py --headed --slowmo 500
"""
import time
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8000"
COOP_SLUG = "chatham"  # the co-op in the local dev DB


def test_member_signup_pay_later(page: Page):
    """Public signup form → Pay Later → confirmation page (no Stripe needed)."""

    unique_email = f"playwright-test-{int(time.time())}@example.com"

    page.goto(f"{BASE_URL}/{COOP_SLUG}")

    page.locator('input[name="membership_type_id"]').first.check()

    page.fill("#first_name", "Jane")
    page.fill("#last_name", "Playwright")
    page.fill("#email", unique_email)
    page.fill("#phone", "5551234567")
    page.fill("#address", "123 Test Street")
    page.fill("#city", "Portland")
    page.select_option("#state", "OR")
    page.fill("#zip", "97201")

    page.check("#agreed_to_terms")
    page.locator('input[name="payment_plan"][value="later"]').check()

    page.click("#submit-btn")

    expect(page.locator("body")).to_contain_text("Jane")
