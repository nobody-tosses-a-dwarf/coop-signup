"""
Happy-path tests for the three main roles:
  - Public visitor  (signup flow)
  - Co-op admin     (dashboard, login)
  - Superadmin      (dashboard, create co-op)

Each test exercises exactly one route end-to-end; no Stripe or email calls are
made (Stripe keys are absent; email_service is stubbed in conftest.py).
"""
import database as db
from conftest import make_csrf_token


class TestPublicRoutes:
    def test_home_page(self, client):
        assert client.get('/').status_code == 200

    def test_signup_page_loads(self, client, test_coop, test_membership_type):
        r = client.get(f'/{test_coop["slug"]}')
        assert r.status_code == 200
        assert 'Test Coop' in r.text

    def test_member_signup_completes(self, client, test_coop, test_membership_type):
        r = client.post(f'/{test_coop["slug"]}/submit', data={
            'csrf_token': make_csrf_token(),
            'membership_type_id': str(test_membership_type['id']),
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': 'jane.doe@example.com',
            'phone': '5551234567',
            'address': '123 Main St',
            'city': 'Portland',
            'state': 'OR',
            'zip': '97201',
            'payment_plan': 'later',
        })
        assert r.status_code == 200
        assert 'Jane' in r.text


class TestAuth:
    def test_admin_redirects_unauthenticated(self, client, test_coop):
        r = client.get(f'/{test_coop["slug"]}/admin', follow_redirects=False)
        assert r.status_code == 302
        assert '/login' in r.headers['location']

    def test_admin_dashboard_loads(self, admin_client, test_coop):
        r = admin_client.get(f'/{test_coop["slug"]}/admin')
        assert r.status_code == 200
        assert 'Test Coop' in r.text

    def test_login_success_redirects_to_admin(self, client, test_coop, test_admin):
        r = client.post('/login', data={
            'csrf_token': make_csrf_token(),
            'username': test_admin['username'],
            'password': test_admin['plaintext_password'],
        }, follow_redirects=False)
        assert r.status_code == 302
        assert test_coop['slug'] in r.headers['location']


class TestSuperadmin:
    def test_superadmin_redirects_unauthenticated(self, client):
        r = client.get('/superadmin', follow_redirects=False)
        assert r.status_code == 302

    def test_superadmin_dashboard_loads(self, superadmin_client):
        r = superadmin_client.get('/superadmin')
        assert r.status_code == 200

    def test_superadmin_creates_coop(self, superadmin_client, superadmin_session):
        r = superadmin_client.post('/superadmin/create-coop', data={
            'csrf_token': make_csrf_token(superadmin_session),
            'name': 'Brand New Coop',
            'slug': 'brand-new-coop',
        }, follow_redirects=False)
        assert r.status_code == 302
        assert db.get_coop_by_slug('brand-new-coop') is not None
