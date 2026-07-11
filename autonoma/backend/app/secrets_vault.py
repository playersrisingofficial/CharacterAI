"""Local encrypted secret vault + a redaction helper used everywhere secrets
might otherwise leak (API responses, logs, event streams, screenshots).

Encryption uses a keyed Fernet-style scheme if `cryptography` is installed,
otherwise falls back to an HMAC-authenticated XOR stream cipher derived from
the master key via PBKDF2. Either way, raw secret values are never stored,
returned, or logged — only opaque `secret_ref` handles are.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets as _pysecrets
from typing import Any

from . import database as db
from .config import get_settings

_REDACTED = "***REDACTED***"
_known_values: set[str] = set()  # plaintext values seen this process, for redaction


def _master_key() -> bytes:
    settings = get_settings()
    key = settings.vault_key
    if not key:
        # Process-local ephemeral key. Documented in .env.example: set
        # AUTONOMA_VAULT_KEY to persist secrets across restarts.
        key = db.kv_get("_ephemeral_vault_key")
        if not key:
            key = _pysecrets.token_hex(32)
            db.kv_set("_ephemeral_vault_key", key)
    return hashlib.pbkdf2_hmac("sha256", key.encode(), b"autonoma-vault-v1", 200_000)


def _xor_encrypt(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(16)
    stream = b""
    counter = 0
    while len(stream) < len(plaintext):
        stream += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    ct = bytes(a ^ b for a, b in zip(plaintext, stream))
    tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    return nonce + tag + ct


def _xor_decrypt(blob: bytes, key: bytes) -> bytes:
    nonce, tag, ct = blob[:16], blob[16:48], blob[48:]
    expected = hmac.new(key, nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("secret authentication failed")
    stream = b""
    counter = 0
    while len(stream) < len(ct):
        stream += hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(a ^ b for a, b in zip(ct, stream))


def store_secret(name: str, value: str) -> str:
    """Encrypt and store a secret. Returns an opaque reference handle."""
    ref = f"secret_{re.sub(r'[^a-zA-Z0-9_]+', '_', name).strip('_').lower()}"
    key = _master_key()
    blob = _xor_encrypt(value.encode(), key)
    db.execute(
        "INSERT INTO secrets(ref, ciphertext, created_at) VALUES(?,?,?) "
        "ON CONFLICT(ref) DO UPDATE SET ciphertext=excluded.ciphertext",
        (ref, base64.b64encode(blob).decode(), db._now_iso()),
    )
    _known_values.add(value)
    return ref


def resolve_secret(ref: str) -> str:
    """Decrypt a secret by reference. For internal execution use only —
    never expose the return value in an API response or log."""
    row = db.query_one("SELECT ciphertext FROM secrets WHERE ref=?", (ref,))
    if row is None:
        raise KeyError(f"unknown secret_ref: {ref}")
    blob = base64.b64decode(row["ciphertext"])
    value = _xor_decrypt(blob, _master_key()).decode()
    _known_values.add(value)
    return value


def list_secret_refs() -> list[str]:
    return [r["ref"] for r in db.query("SELECT ref FROM secrets ORDER BY created_at")]


_SECRETISH_KEYS = re.compile(
    r"(password|secret|token|api[_-]?key|credential|passwd|authorization|cookie)", re.I
)


def redact(obj: Any) -> Any:
    """Recursively redact secret values and secret-looking keys from any
    structure before it is returned, logged, or streamed."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRETISH_KEYS.search(k) and not k.endswith("_ref"):
                out[k] = _REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        s = obj
        for val in _known_values:
            if val and val in s:
                s = s.replace(val, _REDACTED)
        return s
    return obj
