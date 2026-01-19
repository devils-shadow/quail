from __future__ import annotations

import re
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from tests.e2e.utils import get_first_message_id, get_first_message_row, goto_inbox


def test_inbox_loads(page, base_url) -> None:
    goto_inbox(page, base_url)
    expect(page.locator("h1.page-title")).to_have_text("Received Mail")
    expect(page.locator("table.inbox-table--body")).to_be_visible()


def test_inbox_and_message_body_classes(page, base_url) -> None:
    goto_inbox(page, base_url)
    body_class = page.locator("body").get_attribute("class") or ""
    assert "list-view" in body_class
    assert "inbox-view" in body_class

    message_id = get_first_message_id(page)
    page.goto(f"{base_url}/message/{message_id}", wait_until="domcontentloaded")
    page.wait_for_selector(".message-page")
    body_class = page.locator("body").get_attribute("class") or ""
    assert "message-view" in body_class


def test_row_click_opens_message_view(page, base_url) -> None:
    goto_inbox(page, base_url)
    row = get_first_message_row(page)
    with page.expect_navigation(wait_until="domcontentloaded"):
        row.click()
    assert re.search(r"/message/\d+", page.url)
    expect(page.locator(".message-page")).to_be_visible()


def test_message_tabs_switch(page, base_url) -> None:
    goto_inbox(page, base_url)
    message_id = get_first_message_id(page)
    page.goto(f"{base_url}/message/{message_id}", wait_until="domcontentloaded")
    page.wait_for_selector(".tabs")

    attachments_tab = page.locator("[data-tab='attachments']")
    attachments_tab.click()
    expect(attachments_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("[data-tab-panel='attachments']")).to_have_class(re.compile(r"active"))

    text_tab = page.locator("[data-tab='text']")
    text_tab.click()
    expect(text_tab).to_have_attribute("aria-selected", "true")
    expect(page.locator("[data-tab-panel='text']")).to_have_class(re.compile(r"active"))


def test_iframe_attributes_when_present(page, base_url) -> None:
    goto_inbox(page, base_url)
    message_id = get_first_message_id(page)
    page.goto(f"{base_url}/message/{message_id}", wait_until="domcontentloaded")
    frame = page.locator(".message-html-frame")
    if frame.count() == 0:
        pytest.skip("HTML iframe not present; HTML rendering disabled.")
    sandbox = frame.get_attribute("sandbox") or ""
    assert "allow-same-origin" in sandbox
    assert frame.get_attribute("referrerpolicy") == "no-referrer"


def test_theme_persistence(page, base_url) -> None:
    goto_inbox(page, base_url)
    initial_theme = page.evaluate("document.documentElement.dataset.theme || 'light'")
    toggle = page.locator("#theme-toggle")
    toggle.click()
    page.wait_for_timeout(150)
    updated_theme = page.evaluate("document.documentElement.dataset.theme")
    assert updated_theme and updated_theme != initial_theme
    stored_theme = page.evaluate("localStorage.getItem('quailTheme')")
    assert stored_theme == updated_theme

    page.reload(wait_until="domcontentloaded")
    page.wait_for_function(
        "document.documentElement.dataset.theme === localStorage.getItem('quailTheme')"
    )
    reloaded_theme = page.evaluate("document.documentElement.dataset.theme")
    assert reloaded_theme == updated_theme


def test_notification_toggle_persists(browser, base_url) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    context.grant_permissions(["notifications"], origin=base_url)
    page = context.new_page()
    goto_inbox(page, base_url)

    permission = page.evaluate("Notification.permission")
    if permission != "granted":
        context.close()
        pytest.skip(f"Notification permission not granted (got: {permission}).")

    toggle = page.locator("#notify-toggle")
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    stored_value = page.evaluate("localStorage.getItem('quailInboxNotify')")
    assert stored_value == "true"

    page.reload(wait_until="domcontentloaded")
    expect(toggle).to_have_attribute("aria-pressed", "true")

    context.close()


def test_pause_toggle_sets_session_state(page, base_url) -> None:
    goto_inbox(page, base_url)
    pause_button = page.locator("#pause-button")
    pause_button.click()
    stored_value = page.evaluate("sessionStorage.getItem('quailInboxPaused')")
    assert stored_value == "true"
    pause_button.click()
    stored_value = page.evaluate("sessionStorage.getItem('quailInboxPaused')")
    assert stored_value == "false"


def test_trash_hides_selected_rows(page, base_url) -> None:
    goto_inbox(page, base_url)
    row = get_first_message_row(page)
    message_id = row.get_attribute("data-message-id")
    assert message_id

    row.locator("input.message-select").check()
    page.locator("#trash-button").click()
    expect(row).to_have_class(re.compile(r"row-hidden"))
    hidden_ids = page.evaluate("JSON.parse(sessionStorage.getItem('quailHiddenMessages') || '[]')")
    assert message_id in hidden_ids


def test_received_cell_formatting(page, base_url) -> None:
    goto_inbox(page, base_url)
    cell = page.locator(".received-cell[data-received-at]").first
    raw_value = cell.get_attribute("data-received-at") or ""
    display_value = cell.inner_text().strip()
    assert display_value

    if raw_value:
        parsed_ok = page.evaluate("(value) => !Number.isNaN(Date.parse(value))", raw_value)
        if parsed_ok:
            assert cell.get_attribute("title")


def test_filter_propagates_to_links_and_sidebar(page, base_url) -> None:
    goto_inbox(page, base_url)
    row = get_first_message_row(page)
    filter_value = row.locator("td.to-col").inner_text().strip()
    if not filter_value:
        pytest.skip("No to-col value available for filter check.")

    goto_inbox(page, base_url, inbox=filter_value)
    body_current = page.locator("body").get_attribute("data-current-inbox")
    assert body_current == filter_value

    input_value = page.locator("input[name='inbox']").input_value()
    assert input_value == filter_value

    recent_item = page.locator("#recent-inboxes li", has_text=filter_value)
    expect(recent_item.first).to_be_visible()

    rows = page.locator("tr[data-message-id]")
    if rows.count() > 0:
        link = rows.first.locator("a").first
        href = link.get_attribute("href") or ""
        assert f"?inbox={quote(filter_value)}" in href
