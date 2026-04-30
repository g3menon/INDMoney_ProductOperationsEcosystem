"""Security helpers — redaction (Phase 1) + token encryption (Phase 7).

TOKEN_ENCRYPTION_KEY must be a valid Fernet key (URL-safe base64, 32 bytes).
Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import re

from cryptography.fernet import Fernet, InvalidToken

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.I),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"service_role\s+\S+", re.I),
)


def redact_secrets(text: str) -> str:
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


# ── Fernet symmetric encryption for stored OAuth tokens (Phase 7, Rules D7) ──


def encrypt_token(plaintext: str, key: str) -> str:
    """Encrypt an OAuth token string using Fernet (AES-128-CBC + HMAC).

    Args:
        plaintext: The raw token value to encrypt.
        key:       A valid Fernet key string (base64-encoded, 32 bytes).

    Returns:
        A URL-safe base64-encoded ciphertext string suitable for DB storage.

    Raises:
        ValueError: If the key is not a valid Fernet key.
    """
    try:
        f = Fernet(key.encode())
    except Exception as exc:
        raise ValueError(f"Invalid TOKEN_ENCRYPTION_KEY: {exc}") from exc
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet-encrypted token string.

    Args:
        ciphertext: The encrypted token as returned by encrypt_token.
        key:        The same Fernet key used during encryption.

    Returns:
        The original plaintext token string.

    Raises:
        ValueError: If the key is invalid or the ciphertext is tampered/expired.
    """
    try:
        f = Fernet(key.encode())
    except Exception as exc:
        raise ValueError(f"Invalid TOKEN_ENCRYPTION_KEY: {exc}") from exc
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Token decryption failed — key mismatch or tampered data") from exc
