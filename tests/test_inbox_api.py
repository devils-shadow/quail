"""Inbox API response contract coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.helpers import build_client, build_email, insert_message

pytestmark = pytest.mark.api


def test_inbox_api_contract(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        now = datetime.now(tz=timezone.utc)
        message_a = build_email(subject="First", to_addr="user@mail.example.test")
        message_b = build_email(subject="Second", to_addr="user@mail.example.test")
        insert_message(
            settings_obj,
            message=message_a,
            envelope_rcpt="user@mail.example.test",
            received_at=now - timedelta(minutes=10),
        )
        insert_message(
            settings_obj,
            message=message_b,
            envelope_rcpt="user@mail.example.test",
            received_at=now,
        )

        response = client.get("/api/inbox")

        assert response.status_code == 200
        payload = response.json()
        assert "messages" in payload
        assert "is_admin" in payload
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["subject"] == "Second"
        assert payload["messages"][1]["subject"] == "First"
