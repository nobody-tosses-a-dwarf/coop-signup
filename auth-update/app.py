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
import hashlib
import secrets

from database import get_db, init_db, seed_chatham, create_member, _fetchone, _fetchall, DATABASE_URL
from validation import validate_signup
from copos_export import export_members_copos

app = FastAPI(title="Co-op Membership Signup")

SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")

PH = "%s" if DATABASE_URL else "?"


def check_admin(request: Request):
    return request.session.get("admin_authenticated") == True


@app.on_event("startup")
def startup():
    init_db()
    seed_chatham()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db()
    coops = _fetchall(conn, "SELECT slug, name, city, state FROM coops ORDER BY name")
    conn.close()
    return templates.TemplateResponse(request, "home.html", {"coops": coops})


@app.get("/{slug}", response_class=HTMLResponse)
async def signup_form(request: Request, slug: str):
    if slug == "admin":
        return RedirectResponse(url="/")
    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

    membership_types = _fetchall(conn,
        f"SELECT * FROM membership_types WHERE coop_id = {PH} AND active = 1 ORDER BY equity_amount",
        (coop["id"],)
    )
    conn.close()

    return templates.TemplateResponse(request, "signup.html", {
        "coop": coop,
        "membership_types": membership_types,
        "errors": {},
        "values": {}
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
            (coop["id"],)
        )
        conn.close()
        return templates.TemplateResponse(request, "signup.html", {
            "coop": coop,
            "membership_types": membership_types,
            "errors": result,
            "values": data
        })

    existing = _fetchone(conn,
        f"SELECT member_number FROM members WHERE coop_id = {PH} AND email = {PH}",
        (coop["id"], result["email"])
    )
    if existing:
        membership_types = _fetchall(conn,
            f"SELECT * FROM membership_types WHERE coop_id = {PH} AND active = 1 ORDER BY equity_amount",
            (coop["id"],)
        )
        conn.close()
        return templates.TemplateResponse(request, "signup.html", {
            "coop": coop,
            "membership_types": membership_types,
            "errors": {"email": f"This email is already registered (Member #{existing['member_number']})"},
            "values": data
        })

    member_number = create_member(conn, coop["id"], result)
    conn.commit()

    mtype = _fetchone(conn, f"SELECT * FROM membership_types WHERE id = {PH}", (result["membership_type_id"],))
    conn.close()

    return templates.TemplateResponse(request, "confirmation.html", {
        "coop": coop,
        "member_number": member_number,
        "member": result,
        "membership_type": mtype
    })


# ---- Admin routes ----

@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/admin/login", response_class=HTMLResponse)
async def admin_login_submit(request: Request):
    form_data = await request.form()
    password = form_data.get("password", "")

    if password == ADMIN_PASSWORD:
        request.session["admin_authenticated"] = True
        redirect_to = request.query_params.get("next", "/")
        return RedirectResponse(url=redirect_to, status_code=303)
    else:
        return templates.TemplateResponse(request, "login.html", {"error": "Incorrect password"})


@app.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")


@app.get("/admin/{slug}", response_class=HTMLResponse)
async def admin_dashboard(request: Request, slug: str):
    if not check_admin(request):
        return RedirectResponse(url=f"/admin/login?next=/admin/{slug}")

    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

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
        "coop": coop,
        "members": member_data,
        "total_members": len(member_data)
    })


@app.get("/admin/{slug}/export")
async def export_copos(request: Request, slug: str):
    if not check_admin(request):
        return RedirectResponse(url=f"/admin/login?next=/admin/{slug}")

    conn = get_db()
    coop = _fetchone(conn, f"SELECT * FROM coops WHERE slug = {PH}", (slug,))
    if not coop:
        conn.close()
        raise HTTPException(status_code=404, detail="Co-op not found")

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
