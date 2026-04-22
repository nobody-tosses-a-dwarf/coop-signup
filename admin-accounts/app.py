"""
Co-op Membership Signup System
Main application entry point.
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import os
import secrets

from database import (
    get_db, init_db, seed_chatham, seed_superadmin, create_member,
    _fetchone, _fetchall, DATABASE_URL, PH,
    verify_password, create_admin_user, delete_admin_user, reset_admin_password
)
from validation import validate_signup
from copos_export import export_members_copos

app = FastAPI(title="Co-op Membership Signup")

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_current_admin(request):
    """Returns (user_dict, is_superadmin) or (None, False) if not logged in."""
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
    """Check if current admin can access a specific co-op."""
    user, is_super = get_current_admin(request)
    if not user:
        return False
    if is_super:
        return True
    return user["coop_id"] == coop_id


@app.on_event("startup")
def startup():
    init_db()
    seed_chatham()
    seed_superadmin()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db()
    coops = _fetchall(conn, "SELECT slug, name, city, state FROM coops ORDER BY name")
    conn.close()
    return templates.TemplateResponse(request, "home.html", {"coops": coops})


@app.get("/{slug}", response_class=HTMLResponse)
async def signup_form(request: Request, slug: str):
    if slug == "admin":
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
        "member": result, "membership_type": mtype
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
    coops = _fetchall(conn, "SELECT id, name, slug FROM coops ORDER BY name")
    conn.close()

    return templates.TemplateResponse(request, "manage_admins.html", {
        "admins": admins, "coops": coops, "error": None, "success": None
    })


@app.post("/admin/manage/add", response_class=HTMLResponse)
async def admin_manage_add(request: Request):
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
    coops = _fetchall(conn, "SELECT id, name, slug FROM coops ORDER BY name")
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
    coops = _fetchall(conn, "SELECT id, name, slug FROM coops ORDER BY name")
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
        "total_members": len(member_data), "is_superadmin": is_super
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
