import os
import sqlite3
import tempfile
import atexit
import shutil
from unittest.mock import AsyncMock

# ── Environment setup ──────────────────────────────────────────────────────────
# Must happen before any app/database/csrf import so module-level constants
# (SECRET_KEY, _signer, USE_POSTGRES) are initialised with test values.
_TEST_SECRET = 'test-secret-key-for-automated-tests-x1'
os.environ['SECRET_KEY'] = _TEST_SECRET
os.environ['DIGEST_SECRET'] = 'test-digest-secret-key'
for _var in ('DATABASE_URL', 'STRIPE_SECRET_KEY', 'STRIPE_PUBLISHABLE_KEY', 'ADMIN_PASSWORD'):
    os.environ.pop(_var, None)

# ── Isolated test database ─────────────────────────────────────────────────────
_tmp = tempfile.mkdtemp(prefix='coop_test_')
_TEST_DB = os.path.join(_tmp, 'test.db')
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)

import database as db
db.USE_POSTGRES = False
db.get_connection = lambda: sqlite3.connect(_TEST_DB, check_same_thread=False)

# ── Stub external services ─────────────────────────────────────────────────────
import email_service
import mailchimp_service
email_service.send_member_confirmation_email = AsyncMock()
email_service.send_signup_notification = AsyncMock()
email_service.send_password_reset_email = AsyncMock()
email_service.send_admin_welcome_email = AsyncMock()
mailchimp_service.subscribe_member = AsyncMock()

# ── Import app last (triggers db.init_db + db.migrate_db against test DB) ─────
from app import app  # noqa: E402

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer
import csrf as csrf_module

_serializer = URLSafeTimedSerializer(_TEST_SECRET)


def make_session_cookie(data: dict) -> str:
    return _serializer.dumps(data)


def make_csrf_token(session_cookie: str = '') -> str:
    return csrf_module.generate_csrf_token(session_cookie)


# ── Session-scoped fixtures ────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Fresh client per test — prevents session cookies leaking between tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope='session')
def test_coop():
    coop_id = db.create_coop('Test Coop', 'testcoop')
    conn = db.get_connection()
    conn.execute('UPDATE coops SET send_member_emails=0, notify_on_signup=0 WHERE id=?', (coop_id,))
    conn.commit()
    conn.close()
    return db.get_coop_by_slug('testcoop')


@pytest.fixture(scope='session')
def test_membership_type(test_coop):
    type_id = db.create_membership_type(test_coop['id'], 'Basic Member', 100.0)
    types = db.get_membership_types(test_coop['id'])
    return next(t for t in types if t['id'] == type_id)


@pytest.fixture(scope='session')
def test_admin(test_coop):
    password = 'TestAdmin123!'
    temp_pw = db.create_coop_admin('admin@testcoop.com', test_coop['id'])
    admin = db.verify_admin('admin@testcoop.com', temp_pw)
    db.change_admin_password(admin['id'], password)
    return {**admin, 'plaintext_password': password}


@pytest.fixture(scope='session')
def superadmin_user():
    password = 'SuperAdmin123!'
    db.create_superadmin(password)
    admin = db.verify_admin('superadmin', password)
    return {**admin, 'plaintext_password': password}


@pytest.fixture(scope='session')
def admin_session(test_coop, test_admin):
    return make_session_cookie({
        'user_id': test_admin['id'],
        'username': test_admin['username'],
        'email': test_admin['email'],
        'is_superadmin': False,
        'timezone': None,
        'coop_id': test_coop['id'],
        'coop_slug': test_coop['slug'],
    })


@pytest.fixture(scope='session')
def superadmin_session(superadmin_user):
    return make_session_cookie({
        'user_id': superadmin_user['id'],
        'username': superadmin_user['username'],
        'email': superadmin_user['email'],
        'is_superadmin': True,
        'timezone': None,
    })


@pytest.fixture
def admin_client(admin_session):
    """TestClient pre-authenticated as co-op admin."""
    with TestClient(app, cookies={'session': admin_session}) as c:
        yield c


@pytest.fixture
def superadmin_client(superadmin_session):
    """TestClient pre-authenticated as superadmin."""
    with TestClient(app, cookies={'session': superadmin_session}) as c:
        yield c
