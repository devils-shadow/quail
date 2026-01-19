from __future__ import annotations

from tests.e2e.utils import goto_inbox, wait_for_inbox_script


def test_inbox_api_etag_roundtrip(context, base_url) -> None:
    response = context.request.get(f"{base_url}/api/inbox")
    assert response.status == 200
    headers = response.headers
    etag = headers.get("etag") or headers.get("ETag")
    assert etag

    response = context.request.get(f"{base_url}/api/inbox", headers={"If-None-Match": etag})
    assert response.status == 304


def test_ws_or_polling_health(page_with_console, base_url) -> None:
    page, errors = page_with_console
    goto_inbox(page, base_url)
    wait_for_inbox_script(page)
    page.wait_for_timeout(1000)
    state = page.evaluate("""() => ({
        wsEnabled: typeof wsEnabled === "undefined" ? null : wsEnabled,
        hasWs: typeof ws === "undefined" ? false : Boolean(ws),
        wsState: typeof ws === "undefined" || !ws ? null : ws.readyState,
        hasPolling: typeof refreshTimer === "undefined" ? false : refreshTimer !== null
      })""")
    assert state["wsEnabled"] is not None
    if state["wsEnabled"]:
        assert state["hasWs"] or state["hasPolling"]
    else:
        assert state["hasPolling"]

    page.wait_for_timeout(1000)
    assert not errors
