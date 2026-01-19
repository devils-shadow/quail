from __future__ import annotations

import argparse
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def _capture_theme(browser, base_url: str, theme: str, out_dir: Path) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    context.add_init_script(f"localStorage.setItem('quailTheme', '{theme}')")
    page = context.new_page()

    page.goto(f"{base_url}/inbox", wait_until="domcontentloaded")
    page.wait_for_selector("table.inbox-table")
    page.wait_for_function(
        "document.documentElement.dataset.theme === localStorage.getItem('quailTheme')"
    )

    message_row = page.locator("tr[data-message-id]").first
    message_id = message_row.get_attribute("data-message-id")
    if not message_id:
        raise SystemExit("No inbox rows found; seed data required.")

    page.screenshot(path=out_dir / f"inbox-{theme}.png", full_page=True)

    page.goto(f"{base_url}/message/{message_id}", wait_until="domcontentloaded")
    page.wait_for_selector(".message-page")
    page.screenshot(path=out_dir / f"message-{theme}.png", full_page=True)

    context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture inbox/message baselines.")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate baselines (default behavior is to overwrite).",
    )
    args = parser.parse_args()
    base_url = _normalize_base_url(os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    out_dir = Path(__file__).parent / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for theme in ("light", "dark"):
            _capture_theme(browser, base_url, theme, out_dir)
        browser.close()

    if args.update:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
