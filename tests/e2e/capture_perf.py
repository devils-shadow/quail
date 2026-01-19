from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def _normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture lightweight perf baseline.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "artifacts" / "perf_baseline.json"),
        help="Path to write JSON output.",
    )
    args = parser.parse_args()

    base_url = _normalize_base_url(os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        requests: list[str] = []
        page.on("request", lambda req: requests.append(req.url))

        response = page.goto(f"{base_url}/inbox", wait_until="load")
        page.wait_for_function("typeof wsEnabled !== 'undefined'")

        html_bytes = 0
        if response:
            body = response.body()
            html_bytes = len(body)

        nav_entry = page.evaluate("performance.getEntriesByType('navigation')[0] || null")
        resource_count = page.evaluate("performance.getEntriesByType('resource').length")
        ws_enabled = page.evaluate("typeof wsEnabled === 'undefined' ? null : Boolean(wsEnabled)")

        result = {
            "url": f"{base_url}/inbox",
            "html_bytes": html_bytes,
            "request_count": len(requests),
            "resource_count": resource_count,
            "domcontentloaded_ms": nav_entry.get("domContentLoadedEventEnd") if nav_entry else None,
            "load_ms": nav_entry.get("loadEventEnd") if nav_entry else None,
            "ws_enabled": ws_enabled,
        }

        out_path.write_text(json.dumps(result, indent=2))

        context.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
