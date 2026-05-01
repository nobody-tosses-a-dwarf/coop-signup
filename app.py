from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer
import database as db
import copos_export
import validation
import email_service
import mailchimp_service
import csrf as csrf_module
import rate_limit
import stripe as stripe_lib
from pydantic import BaseModel
import qrcode
from io import BytesIO
import os
from typing import Optional
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def attach_csrf_token(request: Request, call_next):
    session_cookie = request.cookies.get('session', '')
    request.state.csrf_token = csrf_module.generate_csrf_token(session_cookie)
    return await call_next(request)


async def check_csrf(request: Request, csrf_token: str = Form(...)):
    session_cookie = request.cookies.get('session', '')
    if not csrf_module.validate_csrf_token(csrf_token, session_cookie):
        raise HTTPException(
            status_code=403,
            detail="Invalid or expired form token. Please reload the page and try again."
        )

# Stripe
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
if STRIPE_SECRET_KEY:
    stripe_lib.api_key = STRIPE_SECRET_KEY

# Session management
SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Initialize database
db.init_db()
db.migrate_db()

# Create superadmin if ADMIN_PASSWORD is set
admin_password = os.getenv('ADMIN_PASSWORD')
if admin_password:
    db.create_superadmin(admin_password)

def get_session_data(request: Request) -> Optional[dict]:
    """Get session data from signed cookie"""
    session_cookie = request.cookies.get('session')
    if not session_cookie:
        return None
    
    try:
        return serializer.loads(session_cookie, max_age=86400)  # 24 hours
    except:
        return None

def create_session_cookie(user_data: dict) -> str:
    """Create signed session cookie"""
    return serializer.dumps(user_data)

def require_auth(request: Request):
    """Dependency to require authentication"""
    session_data = get_session_data(request)
    if not session_data:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return session_data

def require_superadmin(request: Request):
    """Dependency to require superadmin authentication"""
    session_data = require_auth(request)
    if session_data.get('_impersonating'):
        raise HTTPException(status_code=302, headers={"Location": "/superadmin/exit-impersonation"})
    if not session_data.get('is_superadmin'):
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return session_data

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    session_data = get_session_data(request)
    if session_data:
        if session_data.get('is_superadmin'):
            return RedirectResponse("/superadmin", status_code=302)
        else:
            coop = db.get_coop_by_slug(session_data.get('coop_slug'))
            if coop:
                return RedirectResponse(f"/{coop['slug']}/admin", status_code=302)
    
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...),
                _csrf: None = Depends(check_csrf)):
    """Process login"""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    ip_key = f"ip:{client_ip}"
    user_key = f"user:{username.lower().strip()}"

    if await rate_limit.is_rate_limited(ip_key) or await rate_limit.is_rate_limited(user_key):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Too many login attempts. Please wait a few minutes and try again."
        }, status_code=429)

    await rate_limit.record_attempt(ip_key)
    await rate_limit.record_attempt(user_key)

    user = db.verify_admin(username, password)

    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
    # Successful login — reset the per-username counter so a legit user who
    # had earlier failures isn't still locked out on their next session.
    await rate_limit.clear_attempts(user_key)

    # Create session
    session_data = {
        'user_id': user['id'],
        'username': user['username'],
        'email': user['email'],
        'is_superadmin': user['is_superadmin']
    }
    
    if not user['is_superadmin']:
        coop = db.get_coop_by_id(user['coop_id'])
        if not coop:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Your admin account is not linked to a valid co-op. Contact the superadmin."
            })
        session_data['coop_id'] = coop['id']
        session_data['coop_slug'] = coop['slug']
    
    response = RedirectResponse(
        "/superadmin" if user['is_superadmin'] else f"/{session_data['coop_slug']}/admin",
        status_code=302
    )
    response.set_cookie(
        key="session",
        value=create_session_cookie(session_data),
        httponly=True,
        max_age=86400,
        samesite='lax'
    )
    
    return response

@app.get("/logout")
async def logout():
    """Logout"""
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page"""
    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "sent": False,
        "error": None
    })

@app.post("/forgot-password")
async def forgot_password(request: Request, email: str = Form(...),
                          _csrf: None = Depends(check_csrf)):
    """Request password reset"""
    token = db.create_password_reset_token(email)
    
    if token:
        await email_service.send_password_reset_email(email, token)
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "sent": True,
            "error": None
        })
    else:
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "sent": False,
            "error": "Email address not found"
        })

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    """Password reset page"""
    admin = db.verify_reset_token(token)
    
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token,
        "email": admin['email'],
        "error": None
    })

@app.post("/reset-password")
async def reset_password(request: Request, token: str = Form(...),
                         new_password: str = Form(...),
                         confirm_password: str = Form(...),
                         _csrf: None = Depends(check_csrf)):
    """Process password reset"""
    admin = db.verify_reset_token(token)
    
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    if new_password != confirm_password:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "token": token,
            "email": admin['email'],
            "error": "Passwords do not match"
        })
    
    if len(new_password) < 8:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "token": token,
            "email": admin['email'],
            "error": "Password must be at least 8 characters"
        })
    
    success = db.reset_password_with_token(token, new_password)
    
    if success:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "token": None,
            "email": admin['email'],
            "success": True
        })
    else:
        raise HTTPException(status_code=400, detail="Password reset failed")

@app.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, session_data: dict = Depends(require_auth)):
    """Change password page"""
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "email": session_data['email'],
        "error": None,
        "success": False
    })

@app.post("/change-password")
async def change_password(request: Request,
                          current_password: str = Form(...),
                          new_password: str = Form(...),
                          confirm_password: str = Form(...),
                          session_data: dict = Depends(require_auth),
                          _csrf: None = Depends(check_csrf)):
    """Process password change"""
    # Verify current password
    user = db.verify_admin(session_data['username'], current_password)
    
    if not user:
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "email": session_data['email'],
            "error": "Current password is incorrect",
            "success": False
        })
    
    if new_password != confirm_password:
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "email": session_data['email'],
            "error": "New passwords do not match",
            "success": False
        })
    
    if len(new_password) < 8:
        return templates.TemplateResponse("change_password.html", {
            "request": request,
            "email": session_data['email'],
            "error": "Password must be at least 8 characters",
            "success": False
        })
    
    db.change_admin_password(session_data['user_id'], new_password)
    
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "email": session_data['email'],
        "error": None,
        "success": True
    })

@app.get("/superadmin", response_class=HTMLResponse)
async def superadmin_page(request: Request, session_data: dict = Depends(require_superadmin)):
    """Superadmin management page"""
    coops = db.get_all_coops()
    admin_users = db.get_admin_users()

    return templates.TemplateResponse("superadmin.html", {
        "request": request,
        "coops": coops,
        "admin_users": admin_users,
        "session": session_data,
        "admin_email_subject": db.get_system_setting('admin_welcome_subject') or '',
        "admin_email_body": db.get_system_setting('admin_welcome_body') or '',
    })


@app.post("/superadmin/update-email-settings")
async def superadmin_update_email_settings(request: Request,
                                           admin_email_subject: str = Form(''),
                                           admin_email_body: str = Form(''),
                                           session_data: dict = Depends(require_superadmin),
                                           _csrf: None = Depends(check_csrf)):
    """Update the admin welcome email template"""
    try:
        db.update_system_setting('admin_welcome_subject', admin_email_subject.strip() or None)
        db.update_system_setting('admin_welcome_body', admin_email_body.strip() or None)
        return RedirectResponse("/superadmin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating email settings: {str(e)}")

@app.post("/superadmin/create-coop")
async def create_coop(request: Request,
                      name: str = Form(...),
                      slug: str = Form(...),
                      session_data: dict = Depends(require_superadmin),
                      _csrf: None = Depends(check_csrf)):
    """Create a new co-op"""
    # Normalize slug: lowercase, replace spaces with hyphens
    slug = slug.lower().strip().replace(' ', '-')
    
    # Validate slug
    if not validation.validate_slug(slug):
        raise HTTPException(status_code=400, detail="Invalid slug format. Use lowercase letters, numbers, and hyphens only.")
    
    try:
        coop_id = db.create_coop(name, slug)
        return RedirectResponse("/superadmin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating co-op: {str(e)}")

@app.post("/superadmin/create-admin")
async def create_admin(request: Request,
                       email: str = Form(...),
                       coop_id: int = Form(...),
                       session_data: dict = Depends(require_superadmin),
                       _csrf: None = Depends(check_csrf)):
    """Create a new co-op admin"""
    # Validate email
    if not validation.validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    
    try:
        temp_password = db.create_coop_admin(email, coop_id)
        
        # Get coop info
        coops = db.get_all_coops()
        coop_name = next((c['name'] for c in coops if c['id'] == coop_id), "Unknown Co-op")
        
        # Send welcome email with temporary password
        await email_service.send_admin_welcome_email(
            email, coop_name, temp_password,
            custom_subject=db.get_system_setting('admin_welcome_subject') or None,
            custom_body=db.get_system_setting('admin_welcome_body') or None,
        )
        
        return RedirectResponse("/superadmin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating admin: {str(e)}")

@app.post("/superadmin/delete-coop/{coop_id}")
async def delete_coop(request: Request,
                      coop_id: int,
                      password: str = Form(...),
                      session_data: dict = Depends(require_superadmin),
                      _csrf: None = Depends(check_csrf)):
    """Delete a co-op and all related records (requires password confirmation)."""
    # Verify superadmin password
    verified = db.verify_admin(session_data['username'], password)
    if not verified:
        raise HTTPException(status_code=403, detail="Incorrect password")
    
    try:
        deleted = db.delete_coop_cascade(coop_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Co-op not found")
        return RedirectResponse("/superadmin", status_code=302)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting co-op: {str(e)}")

@app.post("/superadmin/delete-admin/{admin_id}")
async def delete_admin(request: Request,
                       admin_id: int,
                       session_data: dict = Depends(require_superadmin),
                       _csrf: None = Depends(check_csrf)):
    """Delete an admin user"""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        if db.USE_POSTGRES:
            cursor.execute('DELETE FROM admin_users WHERE id = %s AND is_superadmin = FALSE', (admin_id,))
        else:
            cursor.execute('DELETE FROM admin_users WHERE id = ? AND is_superadmin = 0', (admin_id,))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse("/superadmin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting admin: {str(e)}")


@app.post("/superadmin/impersonate/{admin_id}")
async def impersonate_admin(request: Request, admin_id: int,
                            session_data: dict = Depends(require_superadmin),
                            _csrf: None = Depends(check_csrf)):
    """Start an impersonation session as a co-op admin."""
    target = db.get_admin_by_id(admin_id)
    if not target or target.get('is_superadmin'):
        raise HTTPException(status_code=404, detail="Admin not found")

    coop_id = target.get('coop_id') if isinstance(target, dict) else target['coop_id']
    coop = db.get_coop_by_id(coop_id)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    target_email = target.get('email') if isinstance(target, dict) else target['email']
    db.log_impersonation(
        superadmin_id=session_data['user_id'],
        superadmin_email=session_data['email'],
        target_admin_id=admin_id,
        target_admin_email=target_email,
        target_coop_name=coop['name'],
    )

    impersonated_session = {
        'user_id': target.get('id') if isinstance(target, dict) else target['id'],
        'username': target.get('username') if isinstance(target, dict) else target['username'],
        'email': target_email,
        'is_superadmin': False,
        'coop_id': coop['id'],
        'coop_slug': coop['slug'],
        '_impersonating': True,
        '_original_superadmin_id': session_data['user_id'],
    }

    response = RedirectResponse(f"/{coop['slug']}/admin", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_cookie(impersonated_session),
        httponly=True,
        max_age=86400,
        samesite='lax',
    )
    return response


@app.get("/superadmin/exit-impersonation")
async def exit_impersonation(request: Request):
    """Restore the superadmin session and return to the superadmin dashboard."""
    session_data = get_session_data(request)
    if not session_data or not session_data.get('_impersonating'):
        return RedirectResponse("/login", status_code=302)

    original_id = session_data.get('_original_superadmin_id')
    original_admin = db.get_admin_by_id(original_id) if original_id else None
    if not original_admin:
        response = RedirectResponse("/login", status_code=302)
        response.delete_cookie("session")
        return response

    superadmin_session = {
        'user_id': original_admin.get('id') if isinstance(original_admin, dict) else original_admin['id'],
        'username': original_admin.get('username') if isinstance(original_admin, dict) else original_admin['username'],
        'email': original_admin.get('email') if isinstance(original_admin, dict) else original_admin['email'],
        'is_superadmin': True,
    }
    response = RedirectResponse("/superadmin", status_code=302)
    response.set_cookie(
        key="session",
        value=create_session_cookie(superadmin_session),
        httponly=True,
        max_age=86400,
        samesite='lax',
    )
    return response


@app.post("/superadmin/coops/{coop_id}/toggle-payments")
async def toggle_coop_payments(request: Request, coop_id: int,
                               session_data: dict = Depends(require_superadmin),
                               _csrf: None = Depends(check_csrf)):
    """Toggle the payment recording UI on or off for a co-op."""
    coops = db.get_all_coops()
    coop = next((c for c in coops if c['id'] == coop_id), None)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    db.update_coop_payments_enabled(coop_id, not coop.get('payments_enabled', True))
    return RedirectResponse("/superadmin", status_code=302)


@app.get("/{slug}", response_class=HTMLResponse)
async def signup_page(request: Request, slug: str, embed: Optional[str] = None):
    """Member signup page"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    membership_types = db.get_membership_types(coop['id'])
    if not membership_types:
        return HTMLResponse(
            content=f"<h1>Membership signup is not yet configured for {coop['name']}</h1>",
            status_code=503
        )
    
    # Check if membership agreement exists and is not empty
    has_agreement = bool(coop.get('membership_agreement') and coop.get('membership_agreement').strip())
    
    # Parse embed options
    embed_options = {}
    if embed:
        parts = embed.split(',')
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                embed_options[key] = value
    
    return templates.TemplateResponse("signup.html", {
        "request": request,
        "coop": coop,
        "membership_types": membership_types,
        "has_agreement": has_agreement,
        "is_embed": embed is not None,
        "embed_options": embed_options,
        "states": validation.US_STATES,
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
        "stripe_connect_account": coop.get('stripe_account_id') or '',
    })

@app.get("/{slug}/membership-agreement", response_class=HTMLResponse)
async def membership_agreement_page(request: Request, slug: str):
    """View membership agreement"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    if not coop.get('membership_agreement'):
        raise HTTPException(status_code=404, detail="Membership agreement not found")
    
    return templates.TemplateResponse("membership_agreement.html", {
        "request": request,
        "coop": coop,
        "agreement_text": coop['membership_agreement']
    })

class PaymentIntentRequest(BaseModel):
    membership_type_id: int
    payment_plan: str


@app.post("/{slug}/create-payment-intent")
async def create_payment_intent(slug: str, body: PaymentIntentRequest):
    """Create a Stripe PaymentIntent for the selected membership type and plan"""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Payments not configured")

    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    membership_types = db.get_membership_types(coop['id'])
    mt = next((t for t in membership_types if t['id'] == body.membership_type_id), None)
    if not mt:
        raise HTTPException(status_code=400, detail="Invalid membership type")

    if body.payment_plan == 'full':
        amount_cents = int(round(float(mt['equity_amount']) * 100))
    elif body.payment_plan == 'installments':
        per_installment = float(mt['equity_amount']) / int(mt['installment_count'])
        amount_cents = int(round(per_installment * 100))
    else:
        raise HTTPException(status_code=400, detail="No payment required for this plan")

    intent_params = dict(
        amount=amount_cents,
        currency='usd',
        metadata={
            'coop_slug': slug,
            'membership_type_id': str(body.membership_type_id),
            'payment_plan': body.payment_plan,
        },
    )
    try:
        stripe_account = coop.get('stripe_account_id')
        if stripe_account:
            intent = stripe_lib.PaymentIntent.create(**intent_params, stripe_account=stripe_account)
        else:
            intent = stripe_lib.PaymentIntent.create(**intent_params)
        return {"client_secret": intent.client_secret}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/{slug}/admin/stripe-connect")
async def stripe_connect(request: Request, slug: str, session_data: dict = Depends(require_auth),
                         _csrf: None = Depends(check_csrf)):
    """Start Stripe Connect Express onboarding for a co-op"""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Stripe is not configured on this platform")

    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    account_id = coop.get('stripe_account_id')
    if not account_id:
        account = stripe_lib.Account.create(type='express')
        account_id = account.id
        db.update_coop_stripe_account(coop['id'], account_id)

    base_domain = os.getenv('BASE_DOMAIN', 'coopsignup.com')
    account_link = stripe_lib.AccountLink.create(
        account=account_id,
        refresh_url=f"https://{base_domain}/{slug}/admin/stripe-onboard",
        return_url=f"https://{base_domain}/{slug}/admin?stripe_connected=1",
        type='account_onboarding',
    )
    return RedirectResponse(account_link.url, status_code=302)


@app.get("/{slug}/admin/stripe-onboard")
async def stripe_onboard_refresh(request: Request, slug: str, session_data: dict = Depends(require_auth)):
    """Refresh a Stripe onboarding link (used as Stripe's refresh_url)"""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="Stripe is not configured on this platform")

    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    account_id = coop.get('stripe_account_id')
    if not account_id:
        return RedirectResponse(f"/{slug}/admin", status_code=302)

    base_domain = os.getenv('BASE_DOMAIN', 'coopsignup.com')
    account_link = stripe_lib.AccountLink.create(
        account=account_id,
        refresh_url=f"https://{base_domain}/{slug}/admin/stripe-onboard",
        return_url=f"https://{base_domain}/{slug}/admin?stripe_connected=1",
        type='account_onboarding',
    )
    return RedirectResponse(account_link.url, status_code=302)


@app.post("/{slug}/admin/stripe-disconnect")
async def stripe_disconnect(request: Request, slug: str, session_data: dict = Depends(require_auth),
                            _csrf: None = Depends(check_csrf)):
    """Disconnect the Stripe account from a co-op"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    db.update_coop_stripe_account(coop['id'], None)
    return RedirectResponse(f"/{slug}/admin", status_code=302)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook — handles account.updated and charge.dispute.created."""
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe_lib.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]

    if event_type == "account.updated":
        account = event["data"]["object"]
        db.update_coop_charges_enabled(account["id"], account["charges_enabled"])

    elif event_type == "charge.dispute.created":
        dispute = event["data"]["object"]
        db.record_dispute(
            stripe_account_id=event.get("account"),
            stripe_dispute_id=dispute["id"],
            stripe_charge_id=dispute["charge"],
            amount=dispute["amount"],
            reason=dispute.get("reason", ""),
            status=dispute["status"],
        )

    return {"status": "ok"}


@app.post("/{slug}/submit")
async def submit_signup(request: Request, slug: str,
                        _csrf: None = Depends(check_csrf),
                        membership_type_id: int = Form(...),
                       first_name: str = Form(...),
                       last_name: str = Form(...),
                       email: str = Form(...),
                       phone: str = Form(...),
                       address: str = Form(...),
                       city: str = Form(...),
                       state: str = Form(...),
                       zip: str = Form(...),
                       payment_plan: str = Form(...),
                       agreed_to_terms: Optional[str] = Form(None),
                       newsletter: Optional[str] = Form(None),
                       payment_intent_id: Optional[str] = Form(None)):
    """Process member signup"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    # Validate agreement checkbox if agreement exists
    if coop.get('membership_agreement') and not agreed_to_terms:
        raise HTTPException(status_code=400, detail="You must agree to the membership agreement")
    
    # Validate inputs
    if not validation.validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    if not validation.validate_phone(phone):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    if not validation.validate_zip(zip):
        raise HTTPException(status_code=400, detail="Invalid ZIP code")

    if state not in validation.US_STATES:
        raise HTTPException(status_code=400, detail="Invalid state")

    if payment_plan not in ['full', 'installments', 'later']:
        raise HTTPException(status_code=400, detail="Invalid payment plan")

    # Verify the membership type belongs to this co-op
    membership_types = db.get_membership_types(coop['id'])
    selected_type = next((t for t in membership_types if t['id'] == membership_type_id), None)
    if not selected_type:
        raise HTTPException(status_code=400, detail="Invalid membership type for this co-op")

    # Checkbox fields: present in form data when checked, absent when not.
    newsletter_opt_in = newsletter is not None

    # Verify Stripe payment if applicable
    stripe_payment_id = None
    equity_paid = 0.0
    payment_date = None

    if STRIPE_SECRET_KEY and payment_plan in ('full', 'installments'):
        if not payment_intent_id:
            raise HTTPException(status_code=400, detail="Payment is required to complete signup")

        # Idempotency: reject if this PaymentIntent was already used to create a member
        if db.member_exists_for_payment(coop['id'], payment_intent_id):
            raise HTTPException(status_code=400, detail="This payment has already been used to complete a signup")

        try:
            stripe_account = coop.get('stripe_account_id')
            if stripe_account:
                intent = stripe_lib.PaymentIntent.retrieve(payment_intent_id, stripe_account=stripe_account)
            else:
                intent = stripe_lib.PaymentIntent.retrieve(payment_intent_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not verify payment")
        if intent.status != 'succeeded':
            raise HTTPException(status_code=400, detail="Payment was not completed")
        if intent.metadata.get('coop_slug') != slug:
            raise HTTPException(status_code=400, detail="Payment does not match this co-op")
        if intent.metadata.get('membership_type_id') != str(membership_type_id):
            raise HTTPException(status_code=400, detail="Payment does not match selected membership type")
        if intent.metadata.get('payment_plan') != payment_plan:
            raise HTTPException(status_code=400, detail="Payment does not match selected payment plan")

        # Recompute the expected charge from the membership type and verify it matches
        if payment_plan == 'full':
            expected_cents = int(round(float(selected_type['equity_amount']) * 100))
        else:  # installments
            per_installment = float(selected_type['equity_amount']) / int(selected_type['installment_count'])
            expected_cents = int(round(per_installment * 100))
        if intent.amount != expected_cents:
            raise HTTPException(status_code=400, detail="Payment amount does not match selected membership")

        stripe_payment_id = intent.id
        equity_paid = intent.amount / 100.0
        from datetime import timezone
        payment_date = datetime.fromtimestamp(intent.created, tz=timezone.utc)

    # Create member
    try:
        result = db.create_member(
            coop['id'], membership_type_id, first_name, last_name,
            email, phone, address, city, state, zip, payment_plan,
            True, newsletter_opt_in,
            stripe_payment_id=stripe_payment_id,
            equity_paid=equity_paid,
            payment_date=payment_date,
        )
        
        # Get membership type info
        membership_types = db.get_membership_types(coop['id'])
        membership_type = next((mt for mt in membership_types if mt['id'] == membership_type_id), None)
        
        # Subscribe to Mailchimp if opted in and co-op has it configured
        if newsletter_opt_in and coop.get('mailchimp_api_key') and coop.get('mailchimp_audience_id'):
            await mailchimp_service.subscribe_member(
                coop['mailchimp_api_key'], coop['mailchimp_audience_id'],
                email, first_name, last_name
            )

        # Send confirmation email (if enabled for this co-op)
        if membership_type and coop.get('send_member_emails', True):
            total_amount = result['equity_amount'] + result['signup_fee']
            await email_service.send_member_confirmation_email(
                email, coop['name'], result['member_number'],
                first_name, membership_type['name'], total_amount, payment_plan,
                last_name=last_name,
                phone=phone,
                address=address,
                city=city,
                state=state,
                zip_code=zip,
                reply_to=coop.get('contact_email') or None,
                custom_subject=coop.get('member_email_subject') or None,
                custom_body=coop.get('member_email_body') or None,
            )
        
        return templates.TemplateResponse("confirmation.html", {
            "request": request,
            "coop": coop,
            "member_number": result['member_number'],
            "first_name": first_name
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating member: {str(e)}")

@app.get("/{slug}/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, slug: str, session_data: dict = Depends(require_auth)):
    """Co-op admin dashboard"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    # Verify this admin belongs to this co-op
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    stripe_just_connected = request.query_params.get('stripe_connected') == '1'

    # Check Stripe Connect account status.
    # Normally use the DB-cached value kept fresh by the webhook.
    # Do one live check right after onboarding to seed the cache immediately.
    stripe_charges_enabled = False
    if STRIPE_SECRET_KEY and coop.get('stripe_account_id'):
        if stripe_just_connected:
            try:
                acct = stripe_lib.Account.retrieve(coop['stripe_account_id'])
                stripe_charges_enabled = acct.charges_enabled
                db.update_coop_charges_enabled(coop['stripe_account_id'], acct.charges_enabled)
            except Exception:
                stripe_charges_enabled = bool(coop.get('charges_enabled'))
        else:
            stripe_charges_enabled = bool(coop.get('charges_enabled'))

    members = db.get_all_members(coop['id'])
    membership_types = db.get_membership_types(coop['id'])
    
    # Calculate stats
    total_members = len(members)
    # Safely calculate total equity, skipping invalid values from old schema
    total_equity = 0
    for m in members:
        try:
            total_equity += float(m['total_equity']) if m['total_equity'] else 0
        except (ValueError, TypeError):
            # Skip invalid data from old schema
            pass
    payment_counts = {
        'full': sum(1 for m in members if m['payment_plan'] == 'full'),
        'installments': sum(1 for m in members if m['payment_plan'] == 'installments'),
        'later': sum(1 for m in members if m['payment_plan'] == 'later')
    }
    
    # Generate embed code
    base_domain = os.getenv('BASE_DOMAIN', 'coopsignup.com')
    embed_code = f'<iframe src="https://{base_domain}/{slug}?embed=1" width="100%" height="800" frameborder="0"></iframe>'
    
    open_disputes = db.get_open_dispute_count(coop['id'])
    export_log = db.get_export_log(coop['id'], limit=5)

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "coop": coop,
        "members": members,
        "membership_types": membership_types,
        "total_members": total_members,
        "total_equity": total_equity,
        "payment_counts": payment_counts,
        "embed_code": embed_code,
        "base_domain": base_domain,
        "session": session_data,
        "states": validation.US_STATES,
        "stripe_configured": bool(STRIPE_SECRET_KEY),
        "stripe_charges_enabled": stripe_charges_enabled,
        "stripe_just_connected": stripe_just_connected,
        "open_disputes": open_disputes,
        "export_log": export_log,
    })

@app.post("/{slug}/admin/membership-types/create")
async def create_membership_type(request: Request, slug: str,
                                 name: str = Form(...),
                                 equity_amount: float = Form(...),
                                 dues_amount: float = Form(0),
                                 signup_fee: float = Form(0),
                                 allows_installments: Optional[str] = Form(None),
                                 installment_count: int = Form(4),
                                 session_data: dict = Depends(require_auth),
                                 _csrf: None = Depends(check_csrf)):
    """Create a membership type"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    # Verify admin access
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        db.create_membership_type(
            coop['id'], name, equity_amount, dues_amount, signup_fee,
            True, installment_count
        )
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating membership type: {str(e)}")

@app.post("/{slug}/admin/membership-types/{type_id}/edit")
async def edit_membership_type(request: Request, slug: str, type_id: int,
                               name: str = Form(...),
                               equity_amount: float = Form(...),
                               dues_amount: float = Form(0),
                               signup_fee: float = Form(0),
                               allows_installments: Optional[str] = Form(None),
                               installment_count: int = Form(4),
                               session_data: dict = Depends(require_auth),
                               _csrf: None = Depends(check_csrf)):
    """Update a membership type"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    try:
        db.update_membership_type(
            type_id, coop['id'], name, equity_amount, dues_amount, signup_fee,
            allows_installments is not None, installment_count
        )
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating membership type: {str(e)}")

@app.post("/{slug}/admin/membership-types/{type_id}/delete")
async def delete_membership_type(request: Request, slug: str, type_id: int,
                                 session_data: dict = Depends(require_auth),
                                 _csrf: None = Depends(check_csrf)):
    """Delete a membership type"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    # Verify admin access
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        db.delete_membership_type(type_id, coop['id'])
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting membership type: {str(e)}")

@app.post("/{slug}/admin/members/{member_id}/edit")
async def edit_member(request: Request, slug: str, member_id: int,
                      first_name: str = Form(...),
                      last_name: str = Form(...),
                      email: str = Form(...),
                      phone: str = Form(...),
                      address: str = Form(...),
                      city: str = Form(...),
                      state: str = Form(...),
                      zip: str = Form(...),
                      payment_plan: str = Form(...),
                      membership_type_id: int = Form(...),
                      session_data: dict = Depends(require_auth),
                      _csrf: None = Depends(check_csrf)):
    """Edit a member's details"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    if not validation.validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if payment_plan not in ['full', 'installments', 'later']:
        raise HTTPException(status_code=400, detail="Invalid payment plan")

    updated = db.update_member(
        member_id, coop['id'], first_name, last_name,
        email, phone, address, city, state, zip, payment_plan, membership_type_id
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Member not found")
    return RedirectResponse(f"/{slug}/admin", status_code=302)


@app.post("/{slug}/admin/members/{member_id}/delete")
async def delete_member_route(request: Request, slug: str, member_id: int,
                              session_data: dict = Depends(require_auth),
                              _csrf: None = Depends(check_csrf)):
    """Delete a member (admins of this co-op, or superadmin)."""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        deleted = db.delete_member(member_id, coop['id'])
        if not deleted:
            raise HTTPException(status_code=404, detail="Member not found")
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting member: {str(e)}")

@app.post("/{slug}/admin/update-branding")
async def update_branding(request: Request, slug: str,
                          logo_url: str = Form(''),
                          welcome_text: str = Form(''),
                          accent_color: str = Form(''),
                          session_data: dict = Depends(require_auth),
                          _csrf: None = Depends(check_csrf)):
    """Save co-op branding settings."""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    if not session_data.get('is_superadmin') and session_data.get('coop_id') != coop['id']:
        raise HTTPException(status_code=403, detail="Access denied")
    import re
    if accent_color and not re.fullmatch(r'#[0-9a-fA-F]{6}', accent_color):
        accent_color = ''
    db.update_coop_branding(coop['id'], logo_url.strip(), welcome_text.strip(), accent_color)
    return RedirectResponse(f"/{slug}/admin", status_code=302)


@app.post("/{slug}/admin/update-agreement")
async def update_agreement(request: Request, slug: str,
                           membership_agreement: str = Form(...),
                           session_data: dict = Depends(require_auth),
                           _csrf: None = Depends(check_csrf)):
    """Update membership agreement"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    # Verify admin access
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        db.update_membership_agreement(coop['id'], membership_agreement)
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating agreement: {str(e)}")

@app.post("/{slug}/admin/update-basic-email")
async def update_basic_email(request: Request, slug: str,
                             contact_email: str = Form(''),
                             send_member_emails: Optional[str] = Form(None),
                             session_data: dict = Depends(require_auth),
                             _csrf: None = Depends(check_csrf)):
    """Update reply-to address and send toggle only, preserving advanced settings"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    try:
        db.update_coop_email_settings(
            coop['id'],
            contact_email.strip() or None,
            send_member_emails is not None,
            coop.get('member_email_subject'),
            coop.get('member_email_body'),
            coop.get('mailchimp_api_key'),
            coop.get('mailchimp_audience_id'),
        )
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating email settings: {str(e)}")


@app.post("/{slug}/admin/update-email-settings")
async def update_email_settings(request: Request, slug: str,
                                contact_email: str = Form(''),
                                send_member_emails: Optional[str] = Form(None),
                                member_email_subject: str = Form(''),
                                member_email_body: str = Form(''),
                                mailchimp_api_key: str = Form(''),
                                mailchimp_audience_id: str = Form(''),
                                session_data: dict = Depends(require_auth),
                                _csrf: None = Depends(check_csrf)):
    """Update email settings for a co-op"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    try:
        db.update_coop_email_settings(
            coop['id'],
            contact_email.strip() or None,
            send_member_emails is not None,
            member_email_subject.strip() or None,
            member_email_body.strip() or None,
            mailchimp_api_key.strip() or None,
            mailchimp_audience_id.strip() or None,
        )
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating email settings: {str(e)}")


@app.get("/{slug}/admin/members/{member_id}/payments", response_class=HTMLResponse)
async def member_payments_page(request: Request, slug: str, member_id: int,
                               session_data: dict = Depends(require_auth)):
    """Payment history and recording page for a single member."""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    member = db.get_member_by_id(member_id, coop['id'])
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    payments = db.get_member_payments(member_id, coop['id'])
    total_paid = sum(float(p['amount']) for p in payments)

    return templates.TemplateResponse("member_payments.html", {
        "request": request,
        "coop": coop,
        "member": member,
        "payments": payments,
        "total_paid": total_paid,
        "today": datetime.now().strftime('%Y-%m-%d'),
    })


@app.post("/{slug}/admin/members/{member_id}/payments/add")
async def add_member_payment(request: Request, slug: str, member_id: int,
                             amount: float = Form(...),
                             payment_date: str = Form(...),
                             method: str = Form(''),
                             notes: str = Form(''),
                             session_data: dict = Depends(require_auth),
                             _csrf: None = Depends(check_csrf)):
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")

    db.add_member_payment(member_id, coop['id'], amount, payment_date, method, notes)
    return RedirectResponse(f"/{slug}/admin/members/{member_id}/payments", status_code=302)


@app.post("/{slug}/admin/members/{member_id}/payments/{payment_id}/delete")
async def delete_member_payment(request: Request, slug: str, member_id: int, payment_id: int,
                                session_data: dict = Depends(require_auth),
                                _csrf: None = Depends(check_csrf)):
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    deleted = db.delete_member_payment(payment_id, coop['id'])
    if not deleted:
        raise HTTPException(status_code=404, detail="Payment record not found")
    return RedirectResponse(f"/{slug}/admin/members/{member_id}/payments", status_code=302)


@app.get("/{slug}/admin/export")
async def export_members(request: Request, slug: str, fmt: str = 'txt',
                         export_type: str = 'delta',
                         session_data: dict = Depends(require_auth)):
    """Export members to CoPOS format. export_type='delta' (default) or 'full'."""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    since_date = None
    if export_type == 'delta':
        since_date = coop.get('last_exported_at')
        members = db.get_members_since(coop['id'], since_date)
    else:
        members = db.get_all_members(coop['id'])

    db.log_export(coop['id'], export_type, len(members), since_date)

    date_str = datetime.now().strftime('%Y%m%d')
    label = 'NEW' if export_type == 'delta' else 'FULL'

    if fmt == 'xlsx':
        content = copos_export.generate_copos_export_xlsx(members, coop)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="MEMBERS-{label}-{date_str}.xlsx"'}
        )
    else:
        content = copos_export.generate_copos_export(members, coop)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="MEMBERS-{label}-{date_str}.TXT"'}
        )

@app.get("/{slug}/qr")
async def get_qr_code(request: Request, slug: str):
    """Generate QR code for signup page"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    base_domain = os.getenv('BASE_DOMAIN', 'coopsignup.com')
    signup_url = f"https://{base_domain}/{slug}"
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(signup_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to bytes
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
