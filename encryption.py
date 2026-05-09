"""Symmetric encryption for sensitive credentials at rest (Mailchimp API keys).

Asymmetric behavior when FERNET_ENCRYPTION_KEY is missing:
  - encrypt() raises RuntimeError — refuses to silently store plaintext
  - decrypt() returns the value unchanged — allows reading legacy data and
    keeps page loads working until the key is set
A warning is printed at import so the misconfiguration is visible in logs.
"""
import os
import sys
from cryptography.fernet import Fernet, InvalidToken

_KEY = os.getenv('FERNET_ENCRYPTION_KEY', '')
_fernet = Fernet(_KEY.encode()) if _KEY else None

if _fernet is None:
    print(
        "WARNING: FERNET_ENCRYPTION_KEY is not set. Mailchimp API keys cannot be "
        "encrypted; saving Mailchimp credentials will fail until this is set.",
        file=sys.stderr,
    )


def encrypt(value: str) -> str:
    if not value:
        return value
    if _fernet is None:
        raise RuntimeError(
            "Cannot encrypt: FERNET_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a Fernet-encrypted value. Returns the original string unchanged
    if encryption is disabled or if the value is legacy plaintext."""
    if not _fernet or not value:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value  # legacy plaintext — will be encrypted on next save
