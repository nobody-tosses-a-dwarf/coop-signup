from fastapi import FastAPI, Request, Form, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer
import database as db
import copos_export
import validation
import email as email_module
import qrcode
from io import BytesIO
import os
from typing import Optional
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Session management
SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Initialize database
db.init_db()

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
        coop = db.get_coop_by_slug(str(user['coop_id']))
        if coop:
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
        await email_module.send_password_reset_email(email, token)
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
        "session": session_data
    })

@app.post("/superadmin/create-coop")
async def create_coop(request: Request,
                     name: str = Form(...),
                     slug: str = Form(...),
                     session_data: dict = Depends(require_superadmin)):
    """Create a new co-op"""
    # Validate slug
    if not validation.validate_slug(slug):
        raise HTTPException(status_code=400, detail="Invalid slug format")
    
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
        await email_module.send_admin_welcome_email(email, coop_name, temp_password)
        
        return RedirectResponse("/superadmin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating admin: {str(e)}")

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
    
    # Check if membership agreement exists
    has_agreement = bool(coop.get('membership_agreement'))
    
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
        "states": validation.US_STATES
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
                       agreed_to_terms: Optional[str] = Form(None)):
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
    
    # Create member
    try:
        result = db.create_member(
            coop['id'], membership_type_id, first_name, last_name,
            email, phone, address, city, state, zip, payment_plan,
            agreed_to_terms='on'
        )
        
        # Get membership type info
        membership_types = db.get_membership_types(coop['id'])
        membership_type = next((mt for mt in membership_types if mt['id'] == membership_type_id), None)
        
        # Send confirmation email
        if membership_type:
            total_amount = result['equity_amount'] + result['signup_fee']
            await email_module.send_member_confirmation_email(
                email, coop['name'], result['member_number'],
                first_name, membership_type['name'], total_amount, payment_plan
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
    total_equity = sum(m['total_equity'] for m in members)
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
            allows_installments='on', installment_count
        )
        return RedirectResponse(f"/{slug}/admin", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating membership type: {str(e)}")

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

@app.get("/{slug}/admin/export")
async def export_members(request: Request, slug: str, session_data: dict = Depends(require_auth)):
    """Export members to CoPOS format"""
    coop = db.get_coop_by_slug(slug)
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")
    
    # Verify admin access
    if not session_data.get('is_superadmin'):
        if session_data.get('coop_id') != coop['id']:
            raise HTTPException(status_code=403, detail="Access denied")
    
    members = db.get_all_members(coop['id'])
    export_content = copos_export.generate_copos_export(members, coop)
    
    filename = f"MEMBERS{datetime.now().strftime('%Y%m%d')}.TXT"
    
    return Response(
        content=export_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
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
