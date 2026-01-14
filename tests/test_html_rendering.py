"""HTML rendering heuristics coverage."""

from __future__ import annotations

import html
import re

import pytest

from quail import db, web
from tests.helpers import build_client, build_email, insert_message

pytestmark = pytest.mark.api


def test_minimal_html_detection_flags_plain_div() -> None:
    assert web._is_minimal_html("<div>Hello</div>") is True


def test_minimal_html_detection_rejects_rich_layout() -> None:
    assert web._is_minimal_html("<table><tr><td>Hi</td></tr></table>") is False
    assert web._is_minimal_html('<img src="x">') is False


def test_message_detail_marks_minimal_html(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        message = build_email(
            subject="Minimal",
            to_addr="user@mail.example.test",
            html_body="<div>Minimal</div>",
        )
        message_row = insert_message(
            settings_obj, message=message, envelope_rcpt="user@mail.example.test"
        )
        db.set_setting(settings_obj.db_path, web.ALLOW_HTML_KEY, "true")

        response = client.get(f"/message/{message_row['id']}")

        assert response.status_code == 200
        assert 'data-minimal="true"' in response.text
        assert 'data-tab="html"' in response.text
        match = re.search(r'srcdoc="([^"]+)"', response.text)
        assert match is not None
        srcdoc = html.unescape(match.group(1))
        assert "<base" in srcdoc


def test_message_detail_skips_minimal_marker_for_rich_html(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        message = build_email(
            subject="Rich",
            to_addr="user@mail.example.test",
            html_body="<table><tr><td>Rich</td></tr></table>",
        )
        message_row = insert_message(
            settings_obj, message=message, envelope_rcpt="user@mail.example.test"
        )
        db.set_setting(settings_obj.db_path, web.ALLOW_HTML_KEY, "true")

        response = client.get(f"/message/{message_row['id']}")

        assert response.status_code == 200
        assert 'data-minimal="true"' not in response.text
