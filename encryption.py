import os
from cryptography.fernet import Fernet, InvalidToken

_KEY = os.getenv('FERNET_ENCRYPTION_KEY', '')
_fernet = Fernet(_KEY.encode()) if _KEY else None


def encrypt(value: str) -> str:
    if not _fernet or not value:
        return value
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
