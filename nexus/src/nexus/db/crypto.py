"""Symmetric encryption for sensitive database fields.

Nexus stores a handful of sensitive values (e.g. saved integration tokens)
encrypted at rest with Fernet (AES-128-CBC + HMAC, from the ``cryptography``
library). The key lives in a single file under the app's data directory,
created lazily with owner-only permissions the first time encryption is
needed -- it is never written into the config file or the database itself,
so a leaked config or a copied ``.db`` doesn't leak the plaintext.

Threading: :class:`FieldCipher` is immutable after construction and Fernet
is safe to share across threads, so one instance can serve the whole app.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from nexus.core.errors import DatabaseError

__all__ = ["FieldCipher"]


class FieldCipher:
    """Encrypts and decrypts short strings for storage in the database."""

    def __init__(self, key: bytes) -> None:
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise DatabaseError("invalid encryption key") from exc

    @classmethod
    def from_key_file(cls, key_path: Path) -> FieldCipher:
        """Load the key at *key_path*, generating it on first use.

        A freshly generated key file is created with ``0600`` permissions
        (owner read/write only) so other users on a shared machine can't
        read it. On platforms without POSIX permissions the chmod is a
        best-effort no-op, which is fine -- the file still isn't exposed
        anywhere Nexus itself shares.
        """
        if key_path.exists():
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            _restrict_permissions(key_path)
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        """Return a URL-safe base64 token for *plaintext* (str in, str out)."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Recover the plaintext for *token*.

        Raises :class:`DatabaseError` if the token was produced with a
        different key or has been tampered with, rather than leaking the
        library's ``InvalidToken`` to callers who only know Nexus errors.
        """
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise DatabaseError("could not decrypt value (wrong key or corrupted data)") from exc


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        # Windows and some filesystems don't support POSIX mode bits.
        _ = os  # keep the import meaningful without failing the operation
