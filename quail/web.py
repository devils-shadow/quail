"""FastAPI entrypoint for Quail UI and API."""

from __future__ import annotations

from fastapi import FastAPI

from quail.logging_config import configure_logging

app = FastAPI(title="Quail")


@app.on_event("startup")
async def _startup() -> None:
    configure_logging()
    # TODO: load settings, ensure DB initialized, and wire routes.


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
