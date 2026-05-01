from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import os

_SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')
_signer = URLSafeTimedSerializer(_SECRET_KEY, salt='csrf')
_MAX_AGE = 3600  # tokens expire after 1 hour


def generate_csrf_token(session_cookie: str = '') -> str:
    payload = session_cookie[:32] if session_cookie else 'anon'
    return _signer.dumps(payload)


def validate_csrf_token(token: str, session_cookie: str = '') -> bool:
    expected = session_cookie[:32] if session_cookie else 'anon'
    try:
        value = _signer.loads(token, max_age=_MAX_AGE)
        return value == expected
    except (BadSignature, SignatureExpired):
        return False
