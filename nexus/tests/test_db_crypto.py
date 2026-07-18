"""Tests for nexus.db.crypto."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from nexus.core.errors import DatabaseError
from nexus.db.crypto import FieldCipher


def test_roundtrip() -> None:
    cipher = FieldCipher(Fernet.generate_key())
    token = cipher.encrypt("sk-secret-value")
    assert token != "sk-secret-value"
    assert cipher.decrypt(token) == "sk-secret-value"


def test_key_file_is_generated_on_first_use(tmp_path: Path) -> None:
    key_path = tmp_path / "nexus.key"
    assert not key_path.exists()
    cipher = FieldCipher.from_key_file(key_path)
    assert key_path.exists()
    assert cipher.decrypt(cipher.encrypt("hi")) == "hi"


def test_key_file_is_reused(tmp_path: Path) -> None:
    key_path = tmp_path / "nexus.key"
    first = FieldCipher.from_key_file(key_path)
    token = first.encrypt("shared")
    second = FieldCipher.from_key_file(key_path)
    assert second.decrypt(token) == "shared"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_generated_key_is_owner_only(tmp_path: Path) -> None:
    key_path = tmp_path / "nexus.key"
    FieldCipher.from_key_file(key_path)
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == (stat.S_IRUSR | stat.S_IWUSR)


def test_wrong_key_raises_database_error() -> None:
    a = FieldCipher(Fernet.generate_key())
    b = FieldCipher(Fernet.generate_key())
    token = a.encrypt("secret")
    with pytest.raises(DatabaseError, match="could not decrypt"):
        b.decrypt(token)


def test_invalid_key_raises() -> None:
    with pytest.raises(DatabaseError, match="invalid encryption key"):
        FieldCipher(b"not-a-valid-fernet-key")
