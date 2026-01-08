"""Security helpers for Quail."""

from __future__ import annotations

from argon2 import PasswordHasher


_PASSWORD_HASHER = PasswordHasher()


def hash_pin(pin: str) -> str:
    return _PASSWORD_HASHER.hash(pin)


def verify_pin(pin: str, stored_hash: str) -> bool:
    return _PASSWORD_HASHER.verify(stored_hash, pin)
