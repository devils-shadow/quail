"""Admin settings validation coverage."""

from __future__ import annotations

import pytest

from quail import db, web
from tests.helpers import build_client, get_csrf_token, unlock_admin

pytestmark = pytest.mark.api


def test_admin_settings_update_persists(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        unlock_admin(client, pin="1234")
        csrf_token = get_csrf_token(client)

        response = client.post(
            "/admin/settings",
            data={
                "allowed_mime_types": "image/png, application/pdf",
                "retention_days": "21",
                "quarantine_retention_days": "5",
                "allow_html": "on",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert db.get_setting(settings_obj.db_path, web.SETTINGS_ALLOWED_MIME_KEY) == (
            "image/png,application/pdf"
        )
        assert db.get_setting(settings_obj.db_path, web.RETENTION_DAYS_KEY) == "21"
        assert db.get_setting(settings_obj.db_path, web.QUARANTINE_RETENTION_DAYS_KEY) == "5"
        assert db.get_setting(settings_obj.db_path, web.ALLOW_HTML_KEY) == "true"


def test_admin_settings_rejects_bad_values(tmp_path, monkeypatch) -> None:
    with build_client(tmp_path, monkeypatch) as (client, settings_obj):
        unlock_admin(client, pin="1234")
        csrf_token = get_csrf_token(client)

        response = client.post(
            "/admin/settings",
            data={
                "allowed_mime_types": "application/pdf",
                "retention_days": "0",
                "quarantine_retention_days": "5",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=retention" in response.headers.get("location", "")
        assert db.get_setting(settings_obj.db_path, web.RETENTION_DAYS_KEY) == (
            web.DEFAULT_RETENTION_DAYS
        )
