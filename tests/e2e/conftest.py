from __future__ import annotations

import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


@pytest.fixture(scope="session")
def base_url() -> str:
    return _normalize_base_url(os.getenv("BASE_URL", "http://127.0.0.1:8000"))


@pytest.fixture(scope="session")
def admin_pin() -> str:
    return os.getenv("QUAIL_E2E_ADMIN_PIN", "")


@pytest.fixture(scope="session")
def browser():
    headless = os.getenv("QUAIL_E2E_HEADLESS", "1") != "0"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, chromium_sandbox=False)
        yield browser
        browser.close()


@pytest.fixture()
def context(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    yield context
    context.close()


@pytest.fixture()
def page(context):
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture()
def page_with_console(context):
    page = context.new_page()
    errors: list[str] = []

    def handle_console(message) -> None:
        if message.type == "error":
            errors.append(message.text)

    def handle_page_error(error) -> None:
        errors.append(str(error))

    page.on("console", handle_console)
    page.on("pageerror", handle_page_error)

    yield page, errors
    page.close()
