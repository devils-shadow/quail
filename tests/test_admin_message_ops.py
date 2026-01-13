"""Admin message delete/clear coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from quail import db
from tests.helpers import (
    build_client,
    build_email,
    insert_attachment,
    insert_message,
    unlock_admin,
)

pytestmark = pytest.mark.api


def _fetch_message_ids(settings_obj) -> set[int]:
    with db.get_connection(settings_obj.db_path) as conn:
        rows = conn.execute("SELECT id FROM messages").fetchall()
    return {int(row["id"]) for row in rows}


def test_admin_delete_message_removes_files(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        unlock_admin(client, pin="1234")

        message = build_email(subject="Delete", to_addr="user@mail.example.test")
        message_row = insert_message(settings_obj, message=message, envelope_rcpt="user@mail.example.test")
        attachment = insert_attachment(
            settings_obj,
            message_id=message_row["id"],
            filename="delete.pdf",
            content_type="application/pdf",
            content=b"delete",
        )

        response = client.post(f"/admin/message/{message_row['id']}/delete", follow_redirects=False)

        assert response.status_code == 303
        assert message_row["id"] not in _fetch_message_ids(settings_obj)
        assert Path(message_row["eml_path"]).exists() is False
        assert Path(attachment["path"]).exists() is False


def test_admin_clear_messages_removes_all(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        unlock_admin(client, pin="1234")

        first = insert_message(
            settings_obj,
            message=build_email(subject="One", to_addr="user@mail.example.test"),
            envelope_rcpt="user@mail.example.test",
        )
        second = insert_message(
            settings_obj,
            message=build_email(subject="Two", to_addr="user@mail.example.test"),
            envelope_rcpt="user@mail.example.test",
        )
        insert_attachment(
            settings_obj,
            message_id=first["id"],
            filename="one.pdf",
            content_type="application/pdf",
            content=b"one",
        )
        insert_attachment(
            settings_obj,
            message_id=second["id"],
            filename="two.pdf",
            content_type="application/pdf",
            content=b"two",
        )

        response = client.post("/admin/messages/clear", follow_redirects=False)

        assert response.status_code == 303
        assert _fetch_message_ids(settings_obj) == set()
        assert Path(first["eml_path"]).exists() is False
        assert Path(second["eml_path"]).exists() is False
