"""
Co-op Membership Signup System
Main application entry point.
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import os
import re
import io
import secrets
import qrcode
import qrcode.image.svg

from database import (
    get_db, init_db, seed_chatham, seed_superadmin, create_member,
    _fetchone, _fetchall, _execute, DATABASE_URL, PH,
    verify_password, create_admin_user, delete_admin_user, reset_admin_password
)
from validation import validate_signup
from copos_export import export_members_copos

app = FastAPI(title="Co-op Membership Signup")

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "coopsignup.com")


def get_current_admin(request):
    user_id = request.session.get("admin_user_id")
    if not user_id:
        return None, False
    conn = get_db()
    user = _fetchone(conn, f"SELECT * FROM admin_users WHERE id = {PH}", (user_id,))
    conn.close()
    if not user:
        return None, False
    return user, bool(user["is_superadmin"])


def admin_can_access_coop(request, coop_id):
    user, is_super = get_current_admin(request)
    if not user:
        return False
    if is_super:
        return True
    return user["coop_id"] == coop_id


def make_slug(name):
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def generate_qr_png(url, size=10):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
                        box_size=size, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@app.on_event("startup")
def startup():
    init_db()
    seed_chatham()
    seed_superadmin()


# ---- QR code endpoint ----

@app.get("/qr/{slug}.png")
async def qr_code_png(slug: str, size: int = 10):
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    conn.close()
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    url = f"https://{BASE_DOMAIN}/{slug}"
    buf = generate_qr_png(url, size=max(5, min(size, 20)))
    return StreamingResponse(buf, media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="qr-{slug}.png"'})


@app.get("/qr/{slug}/download")
async def qr_code_download(slug: str, size: int = 15):
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    conn.close()
    if not coop:
        raise HTTPException(status_code=404, detail="Co-op not found")

    url = f"https://{BASE_DOMAIN}/{slug}"
    buf = generate_qr_png(url, size=max(5, min(size, 30)))
    return StreamingResponse(buf, media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="qr-{slug}.png"'})


# ---- Public routes ----

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db()
    coops = _fetchall(conn, "SELECT slug, name, city, state FROM coops ORDER BY name")
    conn.close()
    return templates.TemplateResponse(request, "home.html", {"coops": coops})


@app.get("/{slug}", response_class=HTMLResponse)
async def signup_form(request: Request, slug: str):
    if slug in ("admin", "qr"):
        return RedirectResponse(url="/admin/login")
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

    membership_types = _fetchall(conn,
        f"SELECT * FROM membership_types WHERE coop_id = {PH} AND active = 1 ORDER BY equity_amount",
        (coop["id"],))
    conn.close()

    return templates.TemplateResponse(request, "signup.html", {
        "coop": coop, "membership_types": membership_types,
        "errors": {}, "values": {}
    })


@app.post("/{slug}/submit", response_class=HTMLResponse)
async def submit_signup(request: Request, slug: str):
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

    form_data = await request.form()
    data = dict(form_data)
    embed_params = data.pop("_embed_params", "")
    is_valid, result = validate_signup(data)

    if not is_valid:
        membership_types = _fetchall(conn,
            f"SELECT * FROM membership_types WHERE coop_id = {PH} AND active = 1 ORDER BY equity_amount",
            (coop["id"],))
        conn.close()
        return templates.TemplateResponse(request, "signup.html", {
            "coop": coop, "membership_types": membership_types,
            "errors": result, "values": data
        })

    existing = _fetchone(conn,
        f"SELECT member_number FROM members WHERE coop_id = {PH} AND email = {PH}",
        (coop["id"], result["email"]))
    if existing:
        membership_types = _fetchall(conn,
            f"SELECT * FROM membership_types WHERE coop_id = {PH} AND active = 1 ORDER BY equity_amount",
            (coop["id"],))
        conn.close()
        return templates.TemplateResponse(request, "signup.html", {
            "coop": coop, "membership_types": membership_types,
            "errors": {"email": f"This email is already registered (Member #{existing['member_number']})"},
            "values": data
        })

    member_number = create_member(conn, coop["id"], result)
    conn.commit()
    mtype = _fetchone(conn, f"SELECT * FROM membership_types WHERE id = {PH}", (result["membership_type_id"],))
    conn.close()

    return templates.TemplateResponse(request, "confirmation.html", {
        "coop": coop, "member_number": member_number,
        "member": result, "membership_type": mtype,
        "embed_params": embed_params
    })


# ---- Admin auth routes ----

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login_submit(request: Request):
    form_data = await request.form()
    username = form_data.get("username", "").strip().lower()
    password = form_data.get("password", "")

    conn = get_db()
    user = _fetchone(conn, f"SELECT * FROM admin_users WHERE username = {PH}", (username,))
    conn.close()

    if user and verify_password(password, user["password_hash"]):
        request.session["admin_user_id"] = user["id"]
        redirect_to = request.query_params.get("next")
        if not redirect_to:
            if user["is_superadmin"]:
                redirect_to = "/admin/manage"
            elif user["coop_id"]:
                conn2 = get_db()
                coop = _fetchone(conn2, f"SELECT slug FROM coops WHERE id = {PH}", (user["coop_id"],))
                conn2.close()
                redirect_to = f"/admin/{coop['slug']}" if coop else "/"
            else:
                redirect_to = "/"
        return RedirectResponse(url=redirect_to, status_code=303)
    else:
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password"})


@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


# ---- Superadmin management ----

@app.get("/admin/manage", response_class=HTMLResponse)
async def admin_manage(request: Request):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login?next=/admin/manage")

    conn = get_db()
    admins = _fetchall(conn, """
        SELECT a.*, c.name as coop_name, c.slug as coop_slug
        FROM admin_users a
        LEFT JOIN coops c ON a.coop_id = c.id
        ORDER BY a.is_superadmin DESC, c.name, a.username
    """)
    coops = _fetchall(conn, "SELECT * FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops, "error": None, "success": None
    })


@app.post("/admin/manage/add-user", response_class=HTMLResponse)
async def admin_manage_add_user(request: Request):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login")

    form_data = await request.form()
    username = form_data.get("username", "").strip().lower()
    password = form_data.get("password", "")
    coop_id = int(form_data.get("coop_id", 0))

    conn = get_db()
    error = None
    success = None

    if len(username) < 3:
        error = "Username must be at least 3 characters"
    elif len(password) < 6:
        error = "Password must be at least 6 characters"
    elif coop_id < 1:
        error = "Please select a co-op"
    else:
        existing = _fetchone(conn, f"SELECT id FROM admin_users WHERE username = {PH}", (username,))
        if existing:
            error = f"Username '{username}' is already taken"
        else:
            create_admin_user(conn, username, password, coop_id)
            success = f"Admin account '{username}' created"

    admins = _fetchall(conn, """
        SELECT a.*, c.name as coop_name, c.slug as coop_slug
        FROM admin_users a
        LEFT JOIN coops c ON a.coop_id = c.id
        ORDER BY a.is_superadmin DESC, c.name, a.username
    """)
    coops = _fetchall(conn, "SELECT * FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops, "error": error, "success": success
    })


@app.post("/admin/manage/add-coop", response_class=HTMLResponse)
async def admin_manage_add_coop(request: Request):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login")

    form_data = await request.form()
    name = form_data.get("coop_name", "").strip()
    city = form_data.get("coop_city", "").strip()
    state = form_data.get("coop_state", "").strip().upper()
    welcome = form_data.get("coop_welcome", "").strip()
    slug = form_data.get("coop_slug", "").strip().lower()

    if not slug:
        slug = make_slug(name)

    conn = get_db()
    error = None
    success = None

    if len(name) < 3:
        error = "Co-op name must be at least 3 characters"
    elif len(slug) < 2:
        error = "Slug must be at least 2 characters"
    elif not re.match(r'^[a-z0-9-]+$', slug):
        error = "Slug can only contain lowercase letters, numbers, and hyphens"
    else:
        existing = _fetchone(conn, f"SELECT id FROM coops WHERE slug = {PH}", (slug,))
        if existing:
            error = f"Slug '{slug}' is already taken"
        else:
            _execute(conn, f"""
                INSERT INTO coops (slug, name, city, state, welcome_text)
                VALUES ({PH}, {PH}, {PH}, {PH}, {PH})
            """, (slug, name, city, state, welcome or f"Join {name}!"))
            conn.commit()
            success = f"Co-op '{name}' created at /{slug}"

    admins = _fetchall(conn, """
        SELECT a.*, c.name as coop_name, c.slug as coop_slug
        FROM admin_users a
        LEFT JOIN coops c ON a.coop_id = c.id
        ORDER BY a.is_superadmin DESC, c.name, a.username
    """)
    coops = _fetchall(conn, "SELECT * FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops, "error": error, "success": success
    })


@app.post("/admin/manage/add-membership-type", response_class=HTMLResponse)
async def admin_manage_add_membership_type(request: Request):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login")

    form_data = await request.form()
    coop_id = int(form_data.get("mt_coop_id", 0))
    name = form_data.get("mt_name", "").strip().lower()
    label = form_data.get("mt_label", "").strip()
    equity = float(form_data.get("mt_equity", 0))
    num_installments = int(form_data.get("mt_installments", 4))
    interval_months = int(form_data.get("mt_interval", 3))

    conn = get_db()
    error = None
    success = None

    if coop_id < 1:
        error = "Please select a co-op"
    elif len(name) < 2:
        error = "Type name must be at least 2 characters"
    elif len(label) < 2:
        error = "Display label must be at least 2 characters"
    elif equity <= 0:
        error = "Equity amount must be greater than 0"
    else:
        existing = _fetchone(conn,
            f"SELECT id FROM membership_types WHERE coop_id = {PH} AND name = {PH}",
            (coop_id, name))
        if existing:
            error = f"Membership type '{name}' already exists for this co-op"
        else:
            _execute(conn, f"""
                INSERT INTO membership_types (coop_id, name, label, equity_amount, dues_amount,
                    signup_fee, installments_allowed, num_installments, installment_interval_months)
                VALUES ({PH}, {PH}, {PH}, {PH}, 0, 0, 1, {PH}, {PH})
            """, (coop_id, name, label, equity, num_installments, interval_months))
            conn.commit()
            success = f"Membership type '{label}' added"

    admins = _fetchall(conn, """
        SELECT a.*, c.name as coop_name, c.slug as coop_slug
        FROM admin_users a
        LEFT JOIN coops c ON a.coop_id = c.id
        ORDER BY a.is_superadmin DESC, c.name, a.username
    """)
    coops = _fetchall(conn, "SELECT * FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops, "error": error, "success": success
    })


@app.post("/admin/manage/delete/{user_id}")
async def admin_manage_delete(request: Request, user_id: int):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login")
    conn = get_db()
    delete_admin_user(conn, user_id)
    conn.close()
    return RedirectResponse(url="/admin/manage", status_code=303)


@app.post("/admin/manage/reset/{user_id}", response_class=HTMLResponse)
async def admin_manage_reset(request: Request, user_id: int):
    user, is_super = get_current_admin(request)
    if not is_super:
        return RedirectResponse(url="/admin/login")

    form_data = await request.form()
    new_password = form_data.get("new_password", "")

    conn = get_db()
    if len(new_password) < 6:
        error = "Password must be at least 6 characters"
    else:
        reset_admin_password(conn, user_id, new_password)
        error = None

    admins = _fetchall(conn, """
        SELECT a.*, c.name as coop_name, c.slug as coop_slug
        FROM admin_users a
        LEFT JOIN coops c ON a.coop_id = c.id
        ORDER BY a.is_superadmin DESC, c.name, a.username
    """)
    coops = _fetchall(conn, "SELECT * FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops,
        "error": error, "success": "Password reset" if not error else None
    })


# ---- Co-op admin dashboard ----

@app.get("/admin/{slug}", response_class=HTMLResponse)
async def admin_dashboard(request: Request, slug: str):
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not admin_can_access_coop(request, coop["id"]):
        conn.close()
        return RedirectResponse(url=f"/admin/login?next=/admin/{slug}")

    user, is_super = get_current_admin(request)

    members = _fetchall(conn, f"""
        SELECT m.*, mt.label as type_label, mt.equity_amount as total_equity
        FROM members m
        JOIN membership_types mt ON m.membership_type_id = mt.id
        WHERE m.coop_id = {PH}
        ORDER BY m.member_number DESC
    """, (coop["id"],))

    member_data = []
    for member in members:
        payments = _fetchone(conn, f"""
            SELECT SUM(CASE WHEN paid = 1 THEN equity_amount ELSE 0 END) as paid_equity,
                   SUM(equity_amount) as total_equity,
                   COUNT(*) as total_payments,
                   SUM(paid) as paid_count
            FROM payments WHERE member_id = {PH}
        """, (member["id"],))
        member_data.append({
            "member": member,
            "paid_equity": payments["paid_equity"] or 0,
            "total_equity": payments["total_equity"] or 0,
            "payments_made": payments["paid_count"] or 0,
            "payments_total": payments["total_payments"] or 0
        })

    conn.close()
    return templates.TemplateResponse(request, "admin.html", {
        "coop": coop, "members": member_data,
        "total_members": len(member_data), "is_superadmin": is_super,
        "base_domain": BASE_DOMAIN
    })


@app.get("/admin/{slug}/export")
async def export_copos(request: Request, slug: str):
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

    if not admin_can_access_coop(request, coop["id"]):
        conn.close()
        return RedirectResponse(url=f"/admin/login?next=/admin/{slug}")

    content = export_members_copos(conn, coop["id"])
    conn.close()

    filename = f"MEMBERS_{slug.upper()}.TXT"
    return PlainTextResponse(
        content=content,
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
