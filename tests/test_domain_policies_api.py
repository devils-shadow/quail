"""API tests for domain policy admin endpoints."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from fastapi.testclient import TestClient

from quail import settings
from quail.web import app
from tests.helpers import get_csrf_token

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
    csrf_token = get_csrf_token(client)
    response = client.post(
        "/admin/unlock",
        data={"pin": pin, "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_domain_policy_requires_admin_session(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        response = client.get(
            "/admin/domain-policies",
            headers={"accept": "application/json"},
        )

        assert response.status_code == 403


def test_domain_policy_create_and_list(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")
        csrf_token = get_csrf_token(client)

        response = client.post(
            "/admin/domain-policies",
            data={
                "domain": "example.com",
                "mode": "RESTRICTED",
                "default_action": "QUARANTINE",
            },
            headers={
                "accept": "application/json",
                "x-admin-pin": "1234",
                "x-csrf-token": csrf_token,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["policy"]["domain"] == "example.com"
        assert payload["policy"]["mode"] == "RESTRICTED"
        assert payload["policy"]["default_action"] == "QUARANTINE"

        list_response = client.get(
            "/admin/domain-policies",
            headers={"accept": "application/json"},
        )
        assert list_response.status_code == 200
        policies = list_response.json()["policies"]
        assert len(policies) == 1
        assert policies[0]["domain"] == "example.com"


def test_domain_policy_rejects_bad_pin(tmp_path, monkeypatch) -> None:
    with _build_client(tmp_path, monkeypatch) as client:
        _unlock_admin(client, pin="1234")
        csrf_token = get_csrf_token(client)

        response = client.post(
            "/admin/domain-policies",
            data={
                "domain": "example.com",
                "mode": "OPEN",
                "default_action": "INBOX",
            },
            headers={
                "accept": "application/json",
                "x-admin-pin": "9999",
                "x-csrf-token": csrf_token,
            },
        )
        assert response.status_code == 403
