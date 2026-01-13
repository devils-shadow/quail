"""Attachment download and inline content coverage."""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from tests.helpers import (
    build_client,
    build_email,
    insert_attachment,
    insert_message,
)

pytestmark = pytest.mark.api


def _build_inline_message() -> EmailMessage:
    message = build_email(
        subject="Inline",
        to_addr="user@mail.example.test",
        text_body="Inline body",
        html_body='<img src="cid:test-cid">',
    )
    html_part = message.get_payload()[1]
    html_part.add_related(
        b"inline-bytes",
        maintype="image",
        subtype="png",
        cid="test-cid",
    )
    return message


def test_attachment_download_returns_file(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        message = build_email(subject="Attachment", to_addr="user@mail.example.test")
        message_row = insert_message(settings_obj, message=message, envelope_rcpt="user@mail.example.test")
        attachment = insert_attachment(
            settings_obj,
            message_id=message_row["id"],
            filename="report.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 test",
        )

        attachment_url = f"/message/{message_row['id']}/attachments/{attachment['id']}"
        response = client.get(attachment_url)

        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 test"
        assert response.headers["content-type"].startswith("application/pdf")
        assert "report.pdf" in response.headers.get("content-disposition", "")


def test_inline_attachment_serves_cid(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        message = _build_inline_message()
        message_row = insert_message(settings_obj, message=message, envelope_rcpt="user@mail.example.test")

        response = client.get(f"/message/{message_row['id']}/inline/test-cid")

        assert response.status_code == 200
        assert response.content == b"inline-bytes"
