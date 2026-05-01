# coop-signup — Claude Code Context

## What this is
Multi-tenant SaaS platform for co-op grocery membership sign-ups.
URL: coopsignup.com (production), demo.coopsignup.com (demo/testing)
Each co-op gets its own slug, membership types, members, and admin users.

## Tech stack
- **Backend**: FastAPI (Python) + Jinja2 templates
- **Database**: PostgreSQL (production) / SQLite (development) — dual-path queries in `database.py`
- **Auth**: `itsdangerous` signed cookies, 24-hour sessions
- **Payments**: Stripe Connect Express — money goes directly to each co-op's Stripe account, not through the platform
- **Email**: configurable reply-to + optional member confirmation emails
- **Exports**: CoPOS tab-delimited (60-column) and Excel (.xlsx) member import files

## Key files
| File | Purpose |
|------|---------|
| `app.py` | All FastAPI routes and business logic |
| `database.py` | All DB access — init, migrations, queries |
| `templates/admin.html` | Co-op admin dashboard (large, complex) |
| `templates/signup.html` | Public member signup form |
| `copos_export.py` | CoPOS export logic (txt + xlsx) |
| `validation.py` | Input validation helpers |
| `email_service.py` | Member confirmation emails |
| `mailchimp_service.py` | Mailchimp list sync |
| `static/style.css` | Global styles for signup page |

## Deploy
**git push → GitHub → Render auto-deploys** (no manual steps needed)

## Environment variables (set in Render, local `.env`)
- `DATABASE_URL` — PostgreSQL connection string (production only)
- `SECRET_KEY` — session signing key
- `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` — platform-level Stripe keys (fallback for demo)
- `ADMIN_PASSWORD` — creates superadmin user on startup
- `SENDGRID_API_KEY` (or similar) — email sending

## Stripe Connect
- Co-ops connect their own Stripe account via `/admin/stripe-connect`
- `coop.stripe_account_id` stores the connected account ID
- Payments use `stripe_account=` param on PaymentIntent to route funds directly
- Co-ops without `stripe_account_id` use platform keys (demo mode)
- `charges_enabled` on the Account object = onboarding complete

## Database notes
- Always add both Postgres (`%s`) and SQLite (`?`) query paths
- Migrations live in `db.migrate_db()` — Postgres uses `DO $$ BEGIN ... EXCEPTION WHEN duplicate_column` pattern; SQLite uses `try/except ALTER TABLE`
- Member list default sort: `member_number DESC` (newest first for display); exports sort `ASC`

## Multi-tenant
- Each co-op identified by `slug` in URL: `/{slug}/`, `/{slug}/admin/`
- Superadmin at `/superadmin/` can manage all co-ops
- `require_auth` dependency checks session + verifies user belongs to that coop

## Staging/folders to ignore
The repo root has old feature-branch folders (`pg-update/`, `auth-update/`, `admin-accounts/`, etc.) — these are stale snapshots, not active code. All live code is at the repo root.
