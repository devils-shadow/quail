"""API tests for address/content rule admin endpoints."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from fastapi.testclient import TestClient

from quail import settings
from quail.web import app

pytestmark = [pytest.mark.api, pytest.mark.integration]


@contextmanager
def _build_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_EML_DIR", tmp_path / "eml")
    monkeypatch.setattr(settings, "DEFAULT_ATTACHMENT_DIR", tmp_path / "att")
    monkeypatch.setattr(settings, "DEFAULT_DB_PATH", tmp_path / "quail.db")
    with TestClient(app) as client:
        yield client


def _unlock_admin(client: TestClient, pin: str = "1234") -> None:
    response = client.post("/admin/unlock", data={"pin": pin}, follow_redirects=False)
    assert response.status_code == 303


def test_rules_require_admin_session(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        response = client.get(
            "/admin/rules",
            params={"domain": "mail.example.test"},
            headers={"accept": "application/json"},
        )

        assert response.status_code == 403


def test_rule_crud_and_test_endpoint(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")

        create_response = client.post(
            "/admin/rules",
            data={
                "domain": "mail.example.test",
                "rule_type": "ALLOW",
                "match_field": "RCPT_LOCALPART",
                "pattern": r"^user$",
                "priority": "1",
                "action": "INBOX",
                "enabled": "1",
                "note": "VIP sender",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert create_response.status_code == 200
        payload = create_response.json()
        rule_id = payload["rule"]["id"]
        assert payload["rule"]["domain"] == "mail.example.test"
        assert payload["rule"]["rule_type"] == "ALLOW"

        list_response = client.get(
            "/admin/rules",
            params={"domain": "mail.example.test"},
            headers={"accept": "application/json"},
        )
        assert list_response.status_code == 200
        rules = list_response.json()["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == rule_id

        update_response = client.put(
            f"/admin/rules/{rule_id}",
            data={
                "rule_type": "ALLOW",
                "match_field": "RCPT_LOCALPART",
                "pattern": r"^user$",
                "priority": "0",
                "action": "INBOX",
                "enabled": "0",
                "note": "Updated",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert update_response.status_code == 200
        updated = update_response.json()["rule"]
        assert updated["priority"] == 0
        assert updated["enabled"] == 0
        assert updated["note"] == "Updated"

        test_response = client.post(
            "/admin/rules/test",
            data={"pattern": r"^user$", "sample": "user"},
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert test_response.status_code == 200
        assert test_response.json()["matched"] is True

        delete_response = client.delete(
            f"/admin/rules/{rule_id}",
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True


def test_rule_validation_and_priority_order(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")

        bad_response = client.post(
            "/admin/rules",
            data={
                "domain": "mail.example.test",
                "rule_type": "ALLOW",
                "match_field": "RCPT_LOCALPART",
                "pattern": "[",
                "priority": "1",
                "action": "INBOX",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert bad_response.status_code == 400
        assert "Invalid regex pattern" in bad_response.json()["detail"]

        first_response = client.post(
            "/admin/rules",
            data={
                "domain": "mail.example.test",
                "rule_type": "ALLOW",
                "match_field": "RCPT_LOCALPART",
                "pattern": r"^first$",
                "priority": "2",
                "action": "INBOX",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        second_response = client.post(
            "/admin/rules",
            data={
                "domain": "mail.example.test",
                "rule_type": "ALLOW",
                "match_field": "RCPT_LOCALPART",
                "pattern": r"^second$",
                "priority": "1",
                "action": "INBOX",
            },
            headers={"accept": "application/json", "x-admin-pin": "1234"},
        )
        assert first_response.status_code == 200
        assert second_response.status_code == 200

        list_response = client.get(
            "/admin/rules",
            params={"domain": "mail.example.test"},
            headers={"accept": "application/json"},
        )
        rules = list_response.json()["rules"]
        assert rules[0]["priority"] == 1
        assert rules[1]["priority"] == 2
