# WebSocket Inbox Upgrade Plan

This document outlines the WebSocket-based refresh system for the inbox UI. It
describes the current implementation and notes remaining hardening work.

## Goals

- Replace periodic polling with WebSocket updates for inbox changes.
- Preserve current functionality and UI behavior without regressions.
- Keep updates smooth, efficient, and visually stable (no full-page reloads).
- Maintain a safe fallback path when WebSockets are unavailable.

## Non-Goals

- Multi-user accounts or per-user inboxes.
- External dependencies (unless multi-worker support is required).
- Rewriting the ingest pipeline or database schema.

## Current Baseline (Implemented)

- `GET /api/inbox` returns the inbox list with ETag support.
- The inbox page polls with ETag-aware fetches and re-renders on changes.
- Admin actions and purge logic update the same message store.
- WebSocket updates are enabled by default. Set `QUAIL_ENABLE_WS=false` in
  `/etc/quail/config.env` to opt out and use polling only.
- WebSocket origin checks allow the current host origin by default; override
  with `QUAIL_ALLOWED_ORIGINS` if needed.
- Inbox event rows are short-lived and purged by the retention job (1 day).

## Architecture

### Server

- Add WebSocket endpoint: `GET /ws/inbox?inbox=<optional>`.
- Maintain a connection manager keyed by inbox filter.
- Emit inbox updates when:
  - Ingest writes new messages.
  - Admin actions delete/restore messages or change status.
  - Purge removes messages.

### Client

- On inbox page load, open WebSocket connection.
- Receive initial `snapshot` payload and render once.
- Receive `delta` payloads for incremental updates.
- If WebSocket fails, fall back to existing polling.

## Single-Process vs Multi-Worker

### Single-Process (current)
- One server process holds all WebSocket connections.
- Broadcast is in-memory and straightforward.
- Lowest complexity and best fit for Quail’s low-volume usage.

### Multi-Worker (future)
- WebSocket connections are split across workers.
- In-memory broadcast only reaches clients on the same worker.
- Requires a shared broker (Redis pub/sub or similar) to broadcast across
  workers.

## Snapshot vs Delta

### Snapshot-Only
- Every update sends the full message list.
- Simple and reliable.
- Higher bandwidth and UI cost for large inboxes.

### Snapshot + Delta (recommended)
- First update is a full snapshot.
- Subsequent updates send only changed rows.
- Requires careful drift handling.

**Drift mitigation:** on reconnect or mismatch, send a fresh snapshot.

## WebSocket Payloads

### Snapshot
```json
{
  "type": "snapshot",
  "messages": [...],
  "etag": "..."
}
```

### Delta
```json
{
  "type": "delta",
  "added": [...],
  "updated": [...],
  "deleted": [123, 456],
  "etag": "..."
}
```

### Ping
```json
{ "type": "ping" }
```

### Error
```json
{ "type": "error", "detail": "..." }
```

## UI Navigation Behavior

### Inbox → Message Detail
- Close the inbox WebSocket when leaving the inbox page.
- Preserve the last snapshot in memory to avoid flicker on return.

### Message Detail → Inbox
- Reconnect WebSocket on return.
- Request a fresh snapshot if:
  - Connection was down.
  - The inbox filter changed.
  - The last known ETag is stale.

### Inbox → Admin Pages
- Close the inbox WebSocket when leaving the inbox page.
- Admin pages do not need a WebSocket unless they show real-time lists.

### Admin → Inbox
- Reconnect and refresh.
- Prefer snapshot on return to avoid missing admin-driven changes.

## Graceful Fallback Strategy

- If WebSocket opens successfully: disable polling.
- If WebSocket drops: start polling every 15–30 seconds.
- If WebSocket reconnects: stop polling again.
- Keep the inbox table stable; avoid full page reloads.

## Remaining Hardening

- Add reconnect backoff and visibility-aware reconnects.
- Add drift detection and forced snapshots on mismatch.

## Connection Lifecycle

- Retry with exponential backoff (e.g., 1s → 2s → 5s → 10s).
- Close connections on tab hidden for long periods to reduce load.
- Reconnect when the tab becomes visible again.

## Security and Access

- WebSocket should honor the same access rules as `/api/inbox`.
- Admin-only data must not be exposed to non-admin users.
- Validate `inbox` filters server-side.

## Pseudo-Code

### Server: Connection Manager
```python
class InboxHub:
    def __init__(self):
        self.connections = {}  # inbox_filter -> set[WebSocket]

    async def connect(self, ws, inbox_filter):
        await ws.accept()
        self.connections.setdefault(inbox_filter, set()).add(ws)

    def disconnect(self, ws, inbox_filter):
        self.connections.get(inbox_filter, set()).discard(ws)

    async def broadcast(self, inbox_filter, payload):
        for ws in list(self.connections.get(inbox_filter, set())):
            await ws.send_json(payload)
```

### Server: WebSocket Endpoint
```python
@app.websocket("/ws/inbox")
async def inbox_ws(ws: WebSocket, inbox: str | None = None):
    await hub.connect(ws, inbox or "")
    snapshot = build_inbox_snapshot(inbox)
    await ws.send_json({"type": "snapshot", **snapshot})
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    finally:
        hub.disconnect(ws, inbox or "")
```

### Server: Event Emitters
```python
def on_ingest(message):
    payload = build_delta_or_snapshot(message)
    hub.broadcast(message.inbox_filter, payload)

def on_admin_change(message):
    payload = build_delta_or_snapshot(message)
    hub.broadcast(message.inbox_filter, payload)
```

### Client: Connection + Fallback
```js
let ws = null;
let pollingTimer = null;

function startWebSocket() {
  ws = new WebSocket(`/ws/inbox?inbox=${currentInbox}`);
  ws.onopen = () => stopPolling();
  ws.onmessage = handleMessage;
  ws.onclose = () => startPolling();
}

function startPolling() {
  if (pollingTimer) return;
  pollingTimer = setInterval(fetchInbox, 20000);
}

function stopPolling() {
  if (!pollingTimer) return;
  clearInterval(pollingTimer);
  pollingTimer = null;
}
```

## Rollout Plan

1) Add WebSocket endpoint + connection manager.
2) Hook broadcasts to ingest/admin/purge events.
3) Add inbox WebSocket client with fallback polling.
4) Add delta support once stable.

## Open Questions

- Do we need multi-worker support (Redis) in the near term?
- Should admin pages also receive live updates?
- Do we keep polling fallback indefinitely or behind a feature flag?
