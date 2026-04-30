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

# Stripe
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
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
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Process login"""
    user = db.verify_admin(username, password)
    
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
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
async def forgot_password(request: Request, email: str = Form(...)):
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
                        confirm_password: str = Form(...)):
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
                         session_data: dict = Depends(require_auth)):
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
                                            session_data: dict = Depends(require_superadmin)):
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
                     session_data: dict = Depends(require_superadmin)):
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
                      session_data: dict = Depends(require_superadmin)):
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
                     session_data: dict = Depends(require_superadmin)):
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
                       session_data: dict = Depends(require_superadmin)):
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

    try:
        intent = stripe_lib.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            metadata={
                'coop_slug': slug,
                'membership_type_id': str(body.membership_type_id),
                'payment_plan': body.payment_plan,
            },
        )
        return {"client_secret": intent.client_secret}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/{slug}/submit")
async def submit_signup(request: Request, slug: str,
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
    
    # Checkbox fields: present in form data when checked, absent when not.
    newsletter_opt_in = newsletter is not None
    
    # Verify Stripe payment if applicable
    stripe_payment_id = None
    equity_paid = 0.0
    payment_date = None

    if STRIPE_SECRET_KEY and payment_plan in ('full', 'installments'):
        if not payment_intent_id:
            raise HTTPException(status_code=400, detail="Payment is required to complete signup")
        try:
            intent = stripe_lib.PaymentIntent.retrieve(payment_intent_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not verify payment")
        if intent.status != 'succeeded':
            raise HTTPException(status_code=400, detail="Payment was not completed")
        if intent.metadata.get('coop_slug') != slug:
            raise HTTPException(status_code=400, detail="Payment does not match this co-op")
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
        "session": session_data
    })

@app.post("/{slug}/admin/membership-types/create")
async def create_membership_type(request: Request, slug: str,
                                name: str = Form(...),
                                equity_amount: float = Form(...),
                                dues_amount: float = Form(0),
                                signup_fee: float = Form(0),
                                allows_installments: Optional[str] = Form(None),
                                installment_count: int = Form(4),
                                session_data: dict = Depends(require_auth)):
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
                               session_data: dict = Depends(require_auth)):
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
                                session_data: dict = Depends(require_auth)):
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
                      session_data: dict = Depends(require_auth)):
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
                              session_data: dict = Depends(require_auth)):
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

@app.post("/{slug}/admin/update-agreement")
async def update_agreement(request: Request, slug: str,
                          membership_agreement: str = Form(...),
                          session_data: dict = Depends(require_auth)):
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

@app.post("/{slug}/admin/update-email-settings")
async def update_email_settings(request: Request, slug: str,
                                 contact_email: str = Form(''),
                                 send_member_emails: Optional[str] = Form(None),
                                 member_email_subject: str = Form(''),
                                 member_email_body: str = Form(''),
                                 mailchimp_api_key: str = Form(''),
                                 mailchimp_audience_id: str = Form(''),
                                 session_data: dict = Depends(require_auth)):
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


@app.get("/{slug}/admin/export")
async def export_members(request: Request, slug: str, fmt: str = 'txt', session_data: dict = Depends(require_auth)):
    """Export members to CoPOS format (txt or xlsx)"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")

    members = db.get_all_members(coop['id'])
    date_str = datetime.now().strftime('%Y%m%d')

    if fmt == 'xlsx':
        content = copos_export.generate_copos_export_xlsx(members, coop)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="MEMBERS{date_str}.xlsx"'}
        )
    else:
        content = copos_export.generate_copos_export(members, coop)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="MEMBERS{date_str}.TXT"'}
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
