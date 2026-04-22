"""
Database models for co-op membership signup system.
Uses PostgreSQL if DATABASE_URL is set, otherwise falls back to SQLite.
"""

import os
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg
    from psycopg.rows import dict_row

    def get_db():
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        return conn

    def _execute(conn, sql, params=None):
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur

    def _fetchone(conn, sql, params=None):
        cur = _execute(conn, sql, params)
        return cur.fetchone()

    def _fetchall(conn, sql, params=None):
        cur = _execute(conn, sql, params)
        return cur.fetchall()

    def init_db():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS coops (
                id SERIAL PRIMARY KEY,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                city TEXT,
                state TEXT,
                logo_url TEXT,
                welcome_text TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS membership_types (
                id SERIAL PRIMARY KEY,
                coop_id INTEGER NOT NULL REFERENCES coops(id),
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                equity_amount REAL NOT NULL,
                dues_amount REAL DEFAULT 0,
                signup_fee REAL DEFAULT 0,
                installments_allowed INTEGER DEFAULT 0,
                num_installments INTEGER DEFAULT 1,
                installment_interval_months INTEGER DEFAULT 3,
                active INTEGER DEFAULT 1,
                UNIQUE(coop_id, name)
            );

            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                coop_id INTEGER NOT NULL REFERENCES coops(id),
                member_number INTEGER NOT NULL,
                name_1 TEXT NOT NULL,
                name_2 TEXT,
                street_address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                membership_type_id INTEGER NOT NULL REFERENCES membership_types(id),
                payment_plan TEXT NOT NULL CHECK(payment_plan IN ('full','installment','deferred')),
                date_joined TEXT NOT NULL,
                member_due_date TEXT,
                active INTEGER DEFAULT 1,
                newsletter INTEGER DEFAULT 1,
                voting_privileges INTEGER DEFAULT 1,
                tax_exempt INTEGER DEFAULT 0,
                senior_discount INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(coop_id, member_number)
            );

            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                member_id INTEGER NOT NULL REFERENCES members(id),
                installment_number INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                equity_amount REAL DEFAULT 0,
                dues_amount REAL DEFAULT 0,
                paid INTEGER DEFAULT 0,
                paid_date TEXT,
                stripe_payment_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                coop_id INTEGER REFERENCES coops(id),
                is_superadmin INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

    def seed_chatham():
        conn = get_db()
        existing = _fetchone(conn, "SELECT id FROM coops WHERE slug = 'chatham'")
        if existing:
            conn.close()
            return

        _execute(conn, """
            INSERT INTO coops (slug, name, city, state, welcome_text)
            VALUES ('chatham', 'Chatham Real Food Market Co-op', 'Chatham', 'NY',
                    'Join your community-owned grocery store! Membership is by household.')
        """)
        coop = _fetchone(conn, "SELECT id FROM coops WHERE slug = 'chatham'")
        coop_id = coop["id"]

        _execute(conn, """
            INSERT INTO membership_types (coop_id, name, label, equity_amount, dues_amount,
                signup_fee, installments_allowed, num_installments, installment_interval_months)
            VALUES (%s, 'household', 'Household Membership', 100.00, 0, 0, 1, 4, 3)
        """, (coop_id,))

        _execute(conn, """
            INSERT INTO membership_types (coop_id, name, label, equity_amount, dues_amount,
                signup_fee, installments_allowed, num_installments, installment_interval_months)
            VALUES (%s, 'business', 'Business Membership', 500.00, 0, 0, 1, 4, 3)
        """, (coop_id,))

        conn.commit()
        conn.close()

    def get_next_member_number(conn, coop_id):
        row = _fetchone(conn,
            "SELECT COALESCE(MAX(member_number), 0) + 1 as next_num FROM members WHERE coop_id = %s",
            (coop_id,)
        )
        return row["next_num"]

    def create_member(conn, coop_id, data):
        member_number = get_next_member_number(conn, coop_id)
        join_date = date.today().isoformat()

        mtype = _fetchone(conn, "SELECT * FROM membership_types WHERE id = %s", (data["membership_type_id"],))

        if data["payment_plan"] == "installment":
            due_date = (date.today() + relativedelta(months=mtype["installment_interval_months"] * mtype["num_installments"])).isoformat()
        else:
            due_date = join_date

        _execute(conn, """
            INSERT INTO members (coop_id, member_number, name_1, name_2, street_address,
                city, state, zip_code, phone, email, membership_type_id, payment_plan,
                date_joined, member_due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            coop_id, member_number, data["name_1"], data.get("name_2", ""),
            data["street_address"], data["city"], data["state"], data["zip_code"],
            data["phone"], data["email"], data["membership_type_id"],
            data["payment_plan"], join_date, due_date
        ))

        member = _fetchone(conn, "SELECT id FROM members WHERE coop_id = %s AND member_number = %s",
            (coop_id, member_number))
        member_id = member["id"]

        equity = mtype["equity_amount"]
        if data["payment_plan"] == "full":
            _execute(conn, """
                INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                VALUES (%s, 1, %s, %s, 0)
            """, (member_id, join_date, equity))
        elif data["payment_plan"] == "installment":
            per_installment = equity / mtype["num_installments"]
            for i in range(mtype["num_installments"]):
                pmt_date = (date.today() + relativedelta(months=mtype["installment_interval_months"] * i)).isoformat()
                _execute(conn, """
                    INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                    VALUES (%s, %s, %s, %s, 0)
                """, (member_id, i + 1, pmt_date, per_installment))
        else:
            _execute(conn, """
                INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                VALUES (%s, 1, %s, %s, 0)
            """, (member_id, join_date, equity))

        return member_number

else:
    import sqlite3

    DB_PATH = os.environ.get("DATABASE_PATH", "coop_members.db")

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _fetchone(conn, sql, params=None):
        return conn.execute(sql, params or ()).fetchone()

    def _fetchall(conn, sql, params=None):
        return conn.execute(sql, params or ()).fetchall()

    def init_db():
        conn = get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS coops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                city TEXT,
                state TEXT,
                logo_url TEXT,
                welcome_text TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS membership_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coop_id INTEGER NOT NULL REFERENCES coops(id),
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                equity_amount REAL NOT NULL,
                dues_amount REAL DEFAULT 0,
                signup_fee REAL DEFAULT 0,
                installments_allowed INTEGER DEFAULT 0,
                num_installments INTEGER DEFAULT 1,
                installment_interval_months INTEGER DEFAULT 3,
                active INTEGER DEFAULT 1,
                UNIQUE(coop_id, name)
            );
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coop_id INTEGER NOT NULL REFERENCES coops(id),
                member_number INTEGER NOT NULL,
                name_1 TEXT NOT NULL,
                name_2 TEXT,
                street_address TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                membership_type_id INTEGER NOT NULL REFERENCES membership_types(id),
                payment_plan TEXT NOT NULL CHECK(payment_plan IN ('full','installment','deferred')),
                date_joined TEXT NOT NULL,
                member_due_date TEXT,
                active INTEGER DEFAULT 1,
                newsletter INTEGER DEFAULT 1,
                voting_privileges INTEGER DEFAULT 1,
                tax_exempt INTEGER DEFAULT 0,
                senior_discount INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(coop_id, member_number)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES members(id),
                installment_number INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                equity_amount REAL DEFAULT 0,
                dues_amount REAL DEFAULT 0,
                paid INTEGER DEFAULT 0,
                paid_date TEXT,
                stripe_payment_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                coop_id INTEGER REFERENCES coops(id),
                is_superadmin INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

    def seed_chatham():
        conn = get_db()
        existing = conn.execute("SELECT id FROM coops WHERE slug = 'chatham'").fetchone()
        if existing:
            conn.close()
            return
        conn.execute("""
            INSERT INTO coops (slug, name, city, state, welcome_text)
            VALUES ('chatham', 'Chatham Real Food Market Co-op', 'Chatham', 'NY',
                    'Join your community-owned grocery store! Membership is by household.')
        """)
        coop_id = conn.execute("SELECT id FROM coops WHERE slug = 'chatham'").fetchone()["id"]
        conn.execute("""
            INSERT INTO membership_types (coop_id, name, label, equity_amount, dues_amount,
                signup_fee, installments_allowed, num_installments, installment_interval_months)
            VALUES (?, 'household', 'Household Membership', 100.00, 0, 0, 1, 4, 3)
        """, (coop_id,))
        conn.execute("""
            INSERT INTO membership_types (coop_id, name, label, equity_amount, dues_amount,
                signup_fee, installments_allowed, num_installments, installment_interval_months)
            VALUES (?, 'business', 'Business Membership', 500.00, 0, 0, 1, 4, 3)
        """, (coop_id,))
        conn.commit()
        conn.close()

    def get_next_member_number(conn, coop_id):
        row = conn.execute(
            "SELECT COALESCE(MAX(member_number), 0) + 1 as next_num FROM members WHERE coop_id = ?",
            (coop_id,)
        ).fetchone()
        return row["next_num"]

    def create_member(conn, coop_id, data):
        member_number = get_next_member_number(conn, coop_id)
        join_date = date.today().isoformat()
        mtype = conn.execute("SELECT * FROM membership_types WHERE id = ?", (data["membership_type_id"],)).fetchone()

        if data["payment_plan"] == "installment":
            due_date = (date.today() + relativedelta(months=mtype["installment_interval_months"] * mtype["num_installments"])).isoformat()
        else:
            due_date = join_date

        conn.execute("""
            INSERT INTO members (coop_id, member_number, name_1, name_2, street_address,
                city, state, zip_code, phone, email, membership_type_id, payment_plan,
                date_joined, member_due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            coop_id, member_number, data["name_1"], data.get("name_2", ""),
            data["street_address"], data["city"], data["state"], data["zip_code"],
            data["phone"], data["email"], data["membership_type_id"],
            data["payment_plan"], join_date, due_date
        ))
        member_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        equity = mtype["equity_amount"]
        if data["payment_plan"] == "full":
            conn.execute("""
                INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                VALUES (?, 1, ?, ?, 0)
            """, (member_id, join_date, equity))
        elif data["payment_plan"] == "installment":
            per_installment = equity / mtype["num_installments"]
            for i in range(mtype["num_installments"]):
                pmt_date = (date.today() + relativedelta(months=mtype["installment_interval_months"] * i)).isoformat()
                conn.execute("""
                    INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                    VALUES (?, ?, ?, ?, 0)
                """, (member_id, i + 1, pmt_date, per_installment))
        else:
            conn.execute("""
                INSERT INTO payments (member_id, installment_number, due_date, equity_amount, dues_amount)
                VALUES (?, 1, ?, ?, 0)
            """, (member_id, join_date, equity))

        return member_number
