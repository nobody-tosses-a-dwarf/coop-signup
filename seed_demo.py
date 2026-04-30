"""
Demo data seeder for coopsignup.com demo site.

Run locally against SQLite:
    python seed_demo.py

Run against Render Postgres:
    $env:DATABASE_URL="postgres://..." ; python seed_demo.py
"""

import os
import sys
import random
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

DATABASE_URL = os.getenv('DATABASE_URL')
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    import psycopg
    def get_conn():
        return psycopg.connect(DATABASE_URL)
    PH = '%s'
else:
    import sqlite3
    def get_conn():
        return sqlite3.connect('coops.db', check_same_thread=False)
    PH = '?'


def ph(n):
    """Return n placeholders for the current DB."""
    return ', '.join([PH] * n)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Co-op definitions (inspired by real startup co-ops)
# ---------------------------------------------------------------------------
COOPS = [
    {
        'name': 'Wild Onion Market',
        'slug': 'wild-onion-market',
        'city': 'Evanston',
        'state': 'IL',
        'zips': ['60201', '60202', '60203', '60208'],
        'admin_email': 'admin@wildonionmarket.coop',
        'member_count': 147,
        'membership_types': [
            {'name': 'Individual', 'equity_amount': 200.00, 'dues_amount': 0,   'signup_fee': 10.00, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Household',  'equity_amount': 300.00, 'dues_amount': 0,   'signup_fee': 10.00, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Senior / Low Income', 'equity_amount': 100.00, 'dues_amount': 0, 'signup_fee': 0, 'allows_installments': False, 'installment_count': 1},
        ],
    },
    {
        'name': 'Fertile Ground Food Co-op',
        'slug': 'fertile-ground',
        'city': 'Raleigh',
        'state': 'NC',
        'zips': ['27601', '27603', '27605', '27607', '27609'],
        'admin_email': 'admin@fertilegroundcoop.coop',
        'member_count': 83,
        'membership_types': [
            {'name': 'Individual Member',  'equity_amount': 150.00, 'dues_amount': 25.00, 'signup_fee': 0, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Founding Household', 'equity_amount': 250.00, 'dues_amount': 40.00, 'signup_fee': 0, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Community Supporter','equity_amount': 50.00,  'dues_amount': 0,     'signup_fee': 0, 'allows_installments': False, 'installment_count': 1},
        ],
    },
    {
        'name': 'Gem City Market',
        'slug': 'gem-city-market',
        'city': 'Dayton',
        'state': 'OH',
        'zips': ['45402', '45403', '45404', '45405', '45406'],
        'admin_email': 'admin@gemcitymarket.coop',
        'member_count': 118,
        'membership_types': [
            {'name': 'Single',   'equity_amount': 175.00, 'dues_amount': 0, 'signup_fee': 5.00, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Household','equity_amount': 275.00, 'dues_amount': 0, 'signup_fee': 5.00, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Lifetime', 'equity_amount': 1000.00,'dues_amount': 0, 'signup_fee': 0,    'allows_installments': True,  'installment_count': 4},
        ],
    },
    {
        'name': 'Prairie Commons Market',
        'slug': 'prairie-commons',
        'city': 'Northfield',
        'state': 'MN',
        'zips': ['55057'],
        'admin_email': 'admin@prairiecommons.coop',
        'member_count': 42,
        'membership_types': [
            {'name': 'Individual', 'equity_amount': 125.00, 'dues_amount': 20.00, 'signup_fee': 0, 'allows_installments': True,  'installment_count': 4},
            {'name': 'Family',     'equity_amount': 200.00, 'dues_amount': 30.00, 'signup_fee': 0, 'allows_installments': True,  'installment_count': 4},
        ],
    },
]

# ---------------------------------------------------------------------------
# Fake member data pools
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    'James','Mary','John','Patricia','Robert','Jennifer','Michael','Linda',
    'William','Barbara','David','Elizabeth','Richard','Susan','Joseph','Jessica',
    'Thomas','Sarah','Charles','Karen','Christopher','Lisa','Daniel','Nancy',
    'Matthew','Betty','Anthony','Margaret','Mark','Sandra','Donald','Ashley',
    'Steven','Dorothy','Paul','Kimberly','Andrew','Emily','Kenneth','Donna',
    'Joshua','Michelle','Kevin','Carol','Brian','Amanda','George','Melissa',
    'Timothy','Deborah','Ronald','Stephanie','Edward','Rebecca','Jason','Sharon',
    'Jeffrey','Laura','Ryan','Cynthia','Jacob','Kathleen','Gary','Amy',
    'Nicholas','Angela','Eric','Shirley','Jonathan','Anna','Stephen','Brenda',
    'Larry','Pamela','Justin','Emma','Scott','Nicole','Brandon','Helen',
    'Benjamin','Samantha','Samuel','Katherine','Raymond','Christine','Gregory','Debra',
    'Frank','Rachel','Alexander','Carolyn','Patrick','Janet','Jack','Catherine',
    'Dennis','Maria','Jerry','Heather','Tyler','Diane','Aaron','Julie',
    'Jose','Joyce','Adam','Victoria','Henry','Kelly','Nathan','Christina',
    'Douglas','Ruth','Zachary','Joan','Peter','Virginia','Kyle','Judith',
]

LAST_NAMES = [
    'Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis',
    'Rodriguez','Martinez','Hernandez','Lopez','Gonzalez','Wilson','Anderson',
    'Thomas','Taylor','Moore','Jackson','Martin','Lee','Perez','Thompson',
    'White','Harris','Sanchez','Clark','Ramirez','Lewis','Robinson','Walker',
    'Young','Allen','King','Wright','Scott','Torres','Nguyen','Hill',
    'Flores','Green','Adams','Nelson','Baker','Hall','Rivera','Campbell',
    'Mitchell','Carter','Roberts','Gomez','Phillips','Evans','Turner','Diaz',
    'Parker','Cruz','Edwards','Collins','Reyes','Stewart','Morris','Morales',
    'Murphy','Cook','Rogers','Gutierrez','Ortiz','Morgan','Cooper','Peterson',
    'Bailey','Reed','Kelly','Howard','Ramos','Kim','Cox','Ward',
    'Richardson','Watson','Brooks','Chavez','Wood','James','Bennett','Gray',
    'Mendoza','Ruiz','Hughes','Price','Alvarez','Castillo','Sanders','Patel',
    'Myers','Long','Ross','Foster','Jimenez','Powell','Jenkins','Perry',
]

STREET_NAMES = [
    'Maple', 'Oak', 'Cedar', 'Pine', 'Elm', 'Washington', 'Lake', 'Hill',
    'Main', 'Park', 'River', 'Sunset', 'Highland', 'Forest', 'Meadow',
    'Lincoln', 'Jefferson', 'Adams', 'Madison', 'Monroe', 'Prairie', 'Valley',
]

STREET_TYPES = ['St', 'Ave', 'Blvd', 'Dr', 'Ln', 'Ct', 'Way', 'Pl', 'Rd']

PAYMENT_PLANS = ['full', 'full', 'full', 'installments', 'installments', 'later']


def fake_phone():
    area = random.randint(200, 999)
    mid  = random.randint(200, 999)
    end  = random.randint(1000, 9999)
    return f"({area}) {mid}-{end}"


def fake_address():
    n    = random.randint(100, 9999)
    name = random.choice(STREET_NAMES)
    typ  = random.choice(STREET_TYPES)
    return f"{n} {name} {typ}"


def fake_email(first, last, coop_slug):
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'hotmail.com', 'protonmail.com']
    tag = random.randint(10, 999)
    return f"{first.lower()}.{last.lower()}{tag}@{random.choice(domains)}"


def random_past_date(days_back=730):
    delta = random.randint(1, days_back)
    return datetime.now(tz=timezone.utc) - timedelta(days=delta)


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

def coop_exists(cursor, slug):
    cursor.execute(f'SELECT id FROM coops WHERE slug = {PH}', (slug,))
    row = cursor.fetchone()
    return row[0] if row else None


def seed():
    conn = get_conn()
    cursor = conn.cursor()

    for coop_def in COOPS:
        slug = coop_def['slug']

        # Skip if already seeded
        existing_id = coop_exists(cursor, slug)
        if existing_id:
            print(f"  [skip] {coop_def['name']} already exists (id={existing_id})")
            continue

        print(f"\n  Creating co-op: {coop_def['name']}")

        # 1. Create co-op
        if USE_POSTGRES:
            cursor.execute(
                f"INSERT INTO coops (name, slug, contact_email) VALUES ({ph(3)}) RETURNING id",
                (coop_def['name'], slug, coop_def['admin_email'])
            )
            coop_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                f"INSERT INTO coops (name, slug, contact_email) VALUES ({ph(3)})",
                (coop_def['name'], slug, coop_def['admin_email'])
            )
            coop_id = cursor.lastrowid

        # 2. Create admin user
        temp_pw = 'demo1234'
        hashed  = hash_password(temp_pw)
        if USE_POSTGRES:
            cursor.execute(
                f"INSERT INTO admin_users (username, email, password_hash, coop_id, is_superadmin) VALUES ({ph(5)})",
                (coop_def['admin_email'], coop_def['admin_email'], hashed, coop_id, False)
            )
        else:
            cursor.execute(
                f"INSERT INTO admin_users (username, email, password_hash, coop_id, is_superadmin) VALUES ({ph(5)})",
                (coop_def['admin_email'], coop_def['admin_email'], hashed, coop_id, 0)
            )
        print(f"    Admin: {coop_def['admin_email']} / {temp_pw}")

        # 3. Create membership types
        type_ids = []
        for mt in coop_def['membership_types']:
            if USE_POSTGRES:
                cursor.execute(
                    f"""INSERT INTO membership_types
                        (coop_id, name, equity_amount, dues_amount, signup_fee, allows_installments, installment_count)
                        VALUES ({ph(7)}) RETURNING id""",
                    (coop_id, mt['name'], mt['equity_amount'], mt['dues_amount'],
                     mt['signup_fee'], mt['allows_installments'], mt['installment_count'])
                )
                type_ids.append(cursor.fetchone()[0])
            else:
                cursor.execute(
                    f"""INSERT INTO membership_types
                        (coop_id, name, equity_amount, dues_amount, signup_fee, allows_installments, installment_count)
                        VALUES ({ph(7)})""",
                    (coop_id, mt['name'], mt['equity_amount'], mt['dues_amount'],
                     mt['signup_fee'], mt['allows_installments'] and 1 or 0, mt['installment_count'])
                )
                type_ids.append(cursor.lastrowid)
        print(f"    Membership types: {len(type_ids)}")

        # 4. Create members
        used_emails = set()
        member_count = coop_def['member_count']
        created = 0

        for _ in range(member_count):
            first = random.choice(FIRST_NAMES)
            last  = random.choice(LAST_NAMES)
            email = fake_email(first, last, slug)
            while email in used_emails:
                email = fake_email(first, last, slug)
            used_emails.add(email)

            phone   = fake_phone()
            address = fake_address()
            city    = coop_def['city']
            state   = coop_def['state']
            zip_code = random.choice(coop_def['zips'])
            plan    = random.choice(PAYMENT_PLANS)
            type_id = random.choice(type_ids)
            signup_dt = random_past_date(730)
            newsletter = random.random() > 0.25

            # Get member number
            if USE_POSTGRES:
                cursor.execute(
                    f'UPDATE coops SET next_member_number = next_member_number + 1 WHERE id = {PH} RETURNING next_member_number - 1',
                    (coop_id,)
                )
                member_number = cursor.fetchone()[0]
            else:
                cursor.execute(f'SELECT next_member_number FROM coops WHERE id = {PH}', (coop_id,))
                member_number = cursor.fetchone()[0]
                cursor.execute(f'UPDATE coops SET next_member_number = {PH} WHERE id = {PH}',
                               (member_number + 1, coop_id))

            # Equity paid for full/installments
            equity_paid = 0.0
            payment_date = None
            if plan in ('full', 'installments'):
                # Get equity amount for this type
                cursor.execute(f'SELECT equity_amount, installment_count FROM membership_types WHERE id = {PH}', (type_id,))
                row = cursor.fetchone()
                if row:
                    eq = float(row[0])
                    ic = int(row[1])
                    equity_paid = eq if plan == 'full' else round(eq / ic, 2)
                    payment_date = signup_dt

            if USE_POSTGRES:
                cursor.execute(
                    f"""INSERT INTO members
                        (coop_id, membership_type_id, member_number, first_name, last_name,
                         email, phone, address, city, state, zip, payment_plan,
                         agreed_to_terms, newsletter, equity_paid, payment_date, signed_up_at)
                        VALUES ({ph(17)})""",
                    (coop_id, type_id, member_number, first, last,
                     email, phone, address, city, state, zip_code, plan,
                     True, newsletter, equity_paid, payment_date, signup_dt)
                )
            else:
                cursor.execute(
                    f"""INSERT INTO members
                        (coop_id, membership_type_id, member_number, first_name, last_name,
                         email, phone, address, city, state, zip, payment_plan,
                         agreed_to_terms, newsletter, equity_paid, payment_date, signed_up_at)
                        VALUES ({ph(17)})""",
                    (coop_id, type_id, member_number, first, last,
                     email, phone, address, city, state, zip_code, plan,
                     1, 1 if newsletter else 0, equity_paid, payment_date, signup_dt.isoformat())
                )
            created += 1

        conn.commit()
        print(f"    Members created: {created}")

    conn.close()
    print("\nDemo seed complete.")


if __name__ == '__main__':
    print(f"Seeding {'PostgreSQL' if USE_POSTGRES else 'SQLite'}...\n")
    seed()
