"""Symmetric encryption of secrets at rest.

We use libsodium SecretBox (XSalsa20-Poly1305 AEAD) with a 32-byte master
key read from disk at first use. Encrypted blobs include the nonce inline
(PyNaCl prepends it for us), so we just store the resulting bytes in
postgres BYTEA columns.
"""

import os
from functools import lru_cache
from pathlib import Path

from nacl.secret import SecretBox

_DEFAULT_KEY_PATH = "/run/secrets/master_key"


@lru_cache(maxsize=1)
def _master_key() -> bytes:
    path = Path(os.environ.get("MAELSTROM_MASTER_KEY_PATH", _DEFAULT_KEY_PATH))
    if not path.exists():
        raise FileNotFoundError(
            f"master key not found at {path}. infra/bootstrap.sh creates it; "
            "compose.prod.yml mounts it as the `master_key` secret.",
        )
    key = path.read_bytes()
    if len(key) != SecretBox.KEY_SIZE:
        raise ValueError(
            f"master key must be {SecretBox.KEY_SIZE} bytes; got {len(key)}",
        )
    return key


def encrypt(plaintext: bytes) -> bytes:
    """Returns ciphertext (nonce + tag + body)."""
    return bytes(SecretBox(_master_key()).encrypt(plaintext))


def decrypt(ciphertext: bytes) -> bytes:
    return bytes(SecretBox(_master_key()).decrypt(ciphertext))


def encrypt_str(plaintext: str) -> bytes:
    return encrypt(plaintext.encode("utf-8"))


def decrypt_str(ciphertext: bytes) -> str:
    return decrypt(ciphertext).decode("utf-8")
