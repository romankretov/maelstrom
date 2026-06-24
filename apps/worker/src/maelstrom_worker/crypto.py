"""Same SecretBox-backed encryption as apps/api/crypto.py — duplicated here
because worker shouldn't import from api."""

import os
from functools import lru_cache
from pathlib import Path

from nacl.secret import SecretBox

_DEFAULT_KEY_PATH = "/run/secrets/master_key"


@lru_cache(maxsize=1)
def _master_key() -> bytes:
    path = Path(os.environ.get("MAELSTROM_MASTER_KEY_PATH", _DEFAULT_KEY_PATH))
    if not path.exists():
        raise FileNotFoundError(f"master key not found at {path}")
    key = path.read_bytes()
    if len(key) != SecretBox.KEY_SIZE:
        raise ValueError(f"master key must be {SecretBox.KEY_SIZE} bytes; got {len(key)}")
    return key


def encrypt(plaintext: bytes) -> bytes:
    return bytes(SecretBox(_master_key()).encrypt(plaintext))


def decrypt(ciphertext: bytes) -> bytes:
    return bytes(SecretBox(_master_key()).decrypt(ciphertext))


def encrypt_str(plaintext: str) -> bytes:
    return encrypt(plaintext.encode("utf-8"))


def decrypt_str(ciphertext: bytes) -> str:
    return decrypt(ciphertext).decode("utf-8")
