from __future__ import annotations

from urllib.parse import quote

import pytest
from playwright.sync_api import TimeoutError


def goto_inbox(page, base_url: str, inbox: str | None = None) -> str:
    url = f"{base_url}/inbox"
    if inbox:
        url = f"{url}?inbox={quote(inbox)}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("table.inbox-table")
    return url


def wait_for_inbox_script(page) -> None:
    page.wait_for_function("typeof wsEnabled !== 'undefined'")


def get_first_message_row(page):
    try:
        page.wait_for_selector("tr[data-message-id]", timeout=5000)
    except TimeoutError:
        pytest.fail("No inbox rows found; seed data required.")
    row = page.locator("tr[data-message-id]").first
    return row


def get_first_message_id(page) -> str:
    row = get_first_message_row(page)
    message_id = row.get_attribute("data-message-id")
    if not message_id:
        pytest.fail("Missing data-message-id on first row.")
    return message_id
