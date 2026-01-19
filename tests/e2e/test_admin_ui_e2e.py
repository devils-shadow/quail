from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.utils import get_first_message_id, goto_inbox


def test_admin_unlock_shows_delete_button(page, base_url, admin_pin) -> None:
    if not admin_pin:
        pytest.skip("Admin PIN not configured for E2E.")
    page.goto(f"{base_url}/admin/unlock", wait_until="domcontentloaded")
    page.fill("#pin", admin_pin)
    page.click("form.admin-unlock-form button[type='submit']")
    page.wait_for_url(re.compile(r".*/admin/settings$"))
    expect(page.locator("h1.page-title")).to_have_text("Admin Settings")

    goto_inbox(page, base_url)
    message_id = get_first_message_id(page)
    page.goto(f"{base_url}/message/{message_id}", wait_until="domcontentloaded")

    delete_form = page.locator(f"form[action='/admin/message/{message_id}/delete']")
    expect(delete_form).to_have_count(1)
    expect(delete_form.locator("button")).to_have_text("Delete")
