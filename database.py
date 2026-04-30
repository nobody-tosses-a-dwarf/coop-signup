import sqlite3
import psycopg
import hashlib
import secrets
import os
from datetime import datetime, timedelta
from typing import Optional

# Determine which database to use
DATABASE_URL = os.getenv('DATABASE_URL')
USE_POSTGRES = DATABASE_URL is not None

def get_connection():
    """Get database connection based on environment"""
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL)
    else:
        return sqlite3.connect('coops.db', check_same_thread=False)

def dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def migrate_db():
    """Migrate existing database to add new columns"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Add email column to admin_users if it doesn't exist
        if USE_POSTGRES:
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='admin_users' AND column_name='email'
                    ) THEN
                        ALTER TABLE admin_users ADD COLUMN email TEXT;
                        UPDATE admin_users SET email = username || '@temp.com' WHERE email IS NULL;
                        ALTER TABLE admin_users ALTER COLUMN email SET NOT NULL;
                        CREATE UNIQUE INDEX IF NOT EXISTS admin_users_email_key ON admin_users(email);
                    END IF;
                END $$;
            """)
            
            # Add password reset columns
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='admin_users' AND column_name='password_reset_token'
                    ) THEN
                        ALTER TABLE admin_users ADD COLUMN password_reset_token TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='admin_users' AND column_name='password_reset_expires'
                    ) THEN
                        ALTER TABLE admin_users ADD COLUMN password_reset_expires TIMESTAMP;
                    END IF;
                END $$;
            """)
            
            # Add coop_id to membership_types if it doesn't exist
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='membership_types' AND column_name='coop_id'
                    ) THEN
                        ALTER TABLE membership_types ADD COLUMN coop_id INTEGER REFERENCES coops(id) ON DELETE CASCADE;
                        -- Link existing types to first coop if any exist
                        UPDATE membership_types SET coop_id = (SELECT id FROM coops LIMIT 1) WHERE coop_id IS NULL;
                        ALTER TABLE membership_types ALTER COLUMN coop_id SET NOT NULL;
                    END IF;
                END $$;
            """)
            
            # Add allows_installments to membership_types if it doesn't exist
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='membership_types' AND column_name='allows_installments'
                    ) THEN
                        ALTER TABLE membership_types ADD COLUMN allows_installments BOOLEAN DEFAULT TRUE;
                    END IF;
                END $$;
            """)
            
            # Add installment_count to membership_types if it doesn't exist
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='membership_types' AND column_name='installment_count'
                    ) THEN
                        ALTER TABLE membership_types ADD COLUMN installment_count INTEGER DEFAULT 4;
                    END IF;
                END $$;
            """)
            
            # Add membership_agreement to coops if it doesn't exist
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='coops' AND column_name='membership_agreement'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN membership_agreement TEXT;
                    END IF;
                END $$;
            """)
            
            # Add agreed_to_terms to members if it doesn't exist
            cursor.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='members' AND column_name='agreed_to_terms'
                    ) THEN
                        ALTER TABLE members ADD COLUMN agreed_to_terms BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            """)
            
            # Add newsletter to members if it doesn't exist
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='members' AND column_name='newsletter'
                    ) THEN
                        ALTER TABLE members ADD COLUMN newsletter BOOLEAN DEFAULT TRUE;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='members' AND column_name='stripe_payment_id'
                    ) THEN
                        ALTER TABLE members ADD COLUMN stripe_payment_id TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='members' AND column_name='equity_paid'
                    ) THEN
                        ALTER TABLE members ADD COLUMN equity_paid DECIMAL(10,2) DEFAULT 0;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='members' AND column_name='payment_date'
                    ) THEN
                        ALTER TABLE members ADD COLUMN payment_date TIMESTAMP;
                    END IF;
                END $$;
            """)

            # Add email settings columns to coops if they don't exist
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='contact_email'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN contact_email TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='send_member_emails'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN send_member_emails BOOLEAN DEFAULT TRUE;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='member_email_subject'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN member_email_subject TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='member_email_body'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN member_email_body TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='mailchimp_api_key'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN mailchimp_api_key TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='mailchimp_audience_id'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN mailchimp_audience_id TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='coops' AND column_name='stripe_account_id'
                    ) THEN
                        ALTER TABLE coops ADD COLUMN stripe_account_id TEXT;
                    END IF;
                END $$;
            """)
        else:
            # SQLite migrations (simpler, just try to add columns)
            try:
                cursor.execute('ALTER TABLE admin_users ADD COLUMN email TEXT')
                cursor.execute("UPDATE admin_users SET email = username || '@temp.com'")
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE admin_users ADD COLUMN password_reset_token TEXT')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE admin_users ADD COLUMN password_reset_expires TIMESTAMP')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE membership_types ADD COLUMN coop_id INTEGER REFERENCES coops(id)')
                cursor.execute('UPDATE membership_types SET coop_id = (SELECT id FROM coops LIMIT 1)')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE membership_types ADD COLUMN allows_installments INTEGER DEFAULT 1')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE membership_types ADD COLUMN installment_count INTEGER DEFAULT 4')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN membership_agreement TEXT')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE members ADD COLUMN agreed_to_terms INTEGER DEFAULT 0')
            except:
                pass
            
            try:
                cursor.execute('ALTER TABLE members ADD COLUMN newsletter INTEGER DEFAULT 1')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE members ADD COLUMN stripe_payment_id TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE members ADD COLUMN equity_paid REAL DEFAULT 0')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE members ADD COLUMN payment_date TIMESTAMP')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN contact_email TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN send_member_emails INTEGER DEFAULT 1')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN member_email_subject TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN member_email_body TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN mailchimp_api_key TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN mailchimp_audience_id TEXT')
            except:
                pass

            try:
                cursor.execute('ALTER TABLE coops ADD COLUMN stripe_account_id TEXT')
            except:
                pass

        conn.commit()
    except Exception as e:
        print(f"Migration warning: {e}")
        conn.rollback()
    finally:
        conn.close()

def init_db():
    """Initialize database schema.
    
    PRE-RELEASE behavior: if legacy schema markers are detected on PostgreSQL,
    all tables are dropped so CREATE TABLE IF NOT EXISTS below can recreate
    them with the current expected columns. Once the legacy markers are gone
    this block is a no-op. Intended to be removed before production launch.
    """
    conn = get_connection()
    if USE_POSTGRES:
        cursor = conn.cursor()
    else:
        conn.row_factory = dict_factory
        cursor = conn.cursor()
    
    # ---- PRE-RELEASE: detect and wipe legacy schema ----
    if USE_POSTGRES:
        cursor.execute("""
            SELECT
              EXISTS(SELECT 1 FROM information_schema.columns
                     WHERE table_name='coops' AND column_name='logo_url')
              OR EXISTS(SELECT 1 FROM information_schema.columns
                        WHERE table_name='members' AND column_name='name_1')
              OR (EXISTS(SELECT 1 FROM information_schema.tables
                         WHERE table_name='coops' AND table_schema='public')
                  AND NOT EXISTS(SELECT 1 FROM information_schema.columns
                                 WHERE table_name='coops' AND column_name='next_member_number'))
        """)
        legacy = cursor.fetchone()[0]
        if legacy:
            print("database.py: Legacy schema detected - dropping all tables for clean recreate.")
            for tbl in ['payment_schedules', 'payments', 'members', 'membership_types', 'admin_users', 'coops']:
                cursor.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
            conn.commit()
    else:
        # SQLite legacy detection: check for any known legacy column
        legacy = False
        try:
            cursor.execute("SELECT logo_url FROM coops LIMIT 1")
            legacy = True
        except Exception:
            pass
        if not legacy:
            try:
                cursor.execute("SELECT name_1 FROM members LIMIT 1")
                legacy = True
            except Exception:
                pass
        if not legacy:
            # coops table exists but missing next_member_number?
            try:
                cursor.execute("SELECT 1 FROM coops LIMIT 1")
                try:
                    cursor.execute("SELECT next_member_number FROM coops LIMIT 1")
                except Exception:
                    legacy = True
            except Exception:
                pass
        if legacy:
            print("database.py: Legacy schema detected - dropping all tables for clean recreate.")
            for tbl in ['payment_schedules', 'payments', 'members', 'membership_types', 'admin_users', 'coops']:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {tbl}")
                except Exception:
                    pass
            conn.commit()
    
    # Coops table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coops (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            next_member_number INTEGER DEFAULT 1,
            membership_agreement TEXT,
            contact_email TEXT,
            send_member_emails BOOLEAN DEFAULT TRUE,
            member_email_subject TEXT,
            member_email_body TEXT,
            mailchimp_api_key TEXT,
            mailchimp_audience_id TEXT,
            stripe_account_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''' if USE_POSTGRES else '''
        CREATE TABLE IF NOT EXISTS coops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            next_member_number INTEGER DEFAULT 1,
            membership_agreement TEXT,
            contact_email TEXT,
            send_member_emails INTEGER DEFAULT 1,
            member_email_subject TEXT,
            member_email_body TEXT,
            mailchimp_api_key TEXT,
            mailchimp_audience_id TEXT,
            stripe_account_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Membership types table (now linked to specific co-op)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS membership_types (
            id SERIAL PRIMARY KEY,
            coop_id INTEGER NOT NULL REFERENCES coops(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            equity_amount DECIMAL(10,2) NOT NULL,
            dues_amount DECIMAL(10,2) DEFAULT 0,
            signup_fee DECIMAL(10,2) DEFAULT 0,
            allows_installments BOOLEAN DEFAULT TRUE,
            installment_count INTEGER DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coop_id, name)
        )
    ''' if USE_POSTGRES else '''
        CREATE TABLE IF NOT EXISTS membership_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coop_id INTEGER NOT NULL REFERENCES coops(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            equity_amount REAL NOT NULL,
            dues_amount REAL DEFAULT 0,
            signup_fee REAL DEFAULT 0,
            allows_installments INTEGER DEFAULT 1,
            installment_count INTEGER DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coop_id, name)
        )
    ''')
    
    # Members table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id SERIAL PRIMARY KEY,
            coop_id INTEGER NOT NULL REFERENCES coops(id) ON DELETE CASCADE,
            membership_type_id INTEGER NOT NULL REFERENCES membership_types(id),
            member_number INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip TEXT NOT NULL,
            payment_plan TEXT NOT NULL,
            total_equity DECIMAL(10,2) NOT NULL,
            total_dues DECIMAL(10,2) DEFAULT 0,
            signup_fee DECIMAL(10,2) DEFAULT 0,
            agreed_to_terms BOOLEAN DEFAULT FALSE,
            newsletter BOOLEAN DEFAULT TRUE,
            stripe_payment_id TEXT,
            equity_paid DECIMAL(10,2) DEFAULT 0,
            payment_date TIMESTAMP,
            signed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coop_id, member_number)
        )
    ''' if USE_POSTGRES else '''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coop_id INTEGER NOT NULL REFERENCES coops(id) ON DELETE CASCADE,
            membership_type_id INTEGER NOT NULL REFERENCES membership_types(id),
            member_number INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            zip TEXT NOT NULL,
            payment_plan TEXT NOT NULL,
            total_equity REAL NOT NULL,
            total_dues REAL DEFAULT 0,
            signup_fee REAL DEFAULT 0,
            agreed_to_terms INTEGER DEFAULT 0,
            newsletter INTEGER DEFAULT 1,
            stripe_payment_id TEXT,
            equity_paid REAL DEFAULT 0,
            payment_date TIMESTAMP,
            signed_up_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coop_id, member_number)
        )
    ''')
    
    # Payment schedules table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_schedules (
            id SERIAL PRIMARY KEY,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            installment_number INTEGER NOT NULL,
            due_date DATE NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            paid BOOLEAN DEFAULT FALSE,
            paid_date TIMESTAMP,
            UNIQUE(member_id, installment_number)
        )
    ''' if USE_POSTGRES else '''
        CREATE TABLE IF NOT EXISTS payment_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            installment_number INTEGER NOT NULL,
            due_date DATE NOT NULL,
            amount REAL NOT NULL,
            paid INTEGER DEFAULT 0,
            paid_date TIMESTAMP,
            UNIQUE(member_id, installment_number)
        )
    ''')
    
    # Admin users table (updated with email and password reset)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            coop_id INTEGER REFERENCES coops(id) ON DELETE CASCADE,
            is_superadmin BOOLEAN DEFAULT FALSE,
            password_reset_token TEXT,
            password_reset_expires TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''' if USE_POSTGRES else '''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            coop_id INTEGER REFERENCES coops(id) ON DELETE CASCADE,
            is_superadmin INTEGER DEFAULT 0,
            password_reset_token TEXT,
            password_reset_expires TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # System settings table (key-value store for superadmin-editable platform settings)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_temp_password(length: int = 12) -> str:
    """Generate a secure random temporary password"""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_reset_token() -> str:
    """Generate a secure password reset token"""
    return secrets.token_urlsafe(32)

def create_superadmin(password: str):
    """Create or update the superadmin account"""
    conn = get_connection()
    cursor = conn.cursor()
    
    hashed = hash_password(password)
    email = "superadmin@coopsignup.com"
    
    if USE_POSTGRES:
        cursor.execute('''
            INSERT INTO admin_users (username, email, password_hash, is_superadmin)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash
        ''', ('superadmin', email, hashed))
    else:
        cursor.execute('SELECT id FROM admin_users WHERE username = ?', ('superadmin',))
        if cursor.fetchone():
            cursor.execute('UPDATE admin_users SET password_hash = ?, email = ? WHERE username = ?',
                         (hashed, email, 'superadmin'))
        else:
            cursor.execute('''
                INSERT INTO admin_users (username, email, password_hash, is_superadmin)
                VALUES (?, ?, ?, 1)
            ''', ('superadmin', email, hashed))
    
    conn.commit()
    conn.close()

def verify_admin(username: str, password: str):
    """Verify admin credentials"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    hashed = hash_password(password)
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT id, username, email, coop_id, is_superadmin
            FROM admin_users WHERE username = %s AND password_hash = %s
        ''', (username, hashed))
        row = cursor.fetchone()
        if row:
            result = {
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'coop_id': row[3],
                'is_superadmin': row[4]
            }
        else:
            result = None
    else:
        cursor.execute('''
            SELECT id, username, email, coop_id, is_superadmin
            FROM admin_users WHERE username = ? AND password_hash = ?
        ''', (username, hashed))
        result = cursor.fetchone()
    
    conn.close()
    return result

def create_coop_admin(email: str, coop_id: int) -> str:
    """Create a co-op admin user with email as username and return temporary password"""
    conn = get_connection()
    cursor = conn.cursor()

    temp_password = generate_temp_password()
    hashed = hash_password(temp_password)

    try:
        if USE_POSTGRES:
            cursor.execute('''
                INSERT INTO admin_users (username, email, password_hash, coop_id, is_superadmin)
                VALUES (%s, %s, %s, %s, FALSE)
            ''', (email, email, hashed, coop_id))
            cursor.execute('''
                UPDATE coops SET contact_email = %s
                WHERE id = %s AND (contact_email IS NULL OR contact_email = '')
            ''', (email, coop_id))
        else:
            cursor.execute('''
                INSERT INTO admin_users (username, email, password_hash, coop_id, is_superadmin)
                VALUES (?, ?, ?, ?, 0)
            ''', (email, email, hashed, coop_id))
            cursor.execute('''
                UPDATE coops SET contact_email = ?
                WHERE id = ? AND (contact_email IS NULL OR contact_email = '')
            ''', (email, coop_id))

        conn.commit()
        return temp_password
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def change_admin_password(admin_id: int, new_password: str):
    """Change an admin user's password"""
    conn = get_connection()
    cursor = conn.cursor()
    
    hashed = hash_password(new_password)
    
    if USE_POSTGRES:
        cursor.execute('UPDATE admin_users SET password_hash = %s WHERE id = %s',
                      (hashed, admin_id))
    else:
        cursor.execute('UPDATE admin_users SET password_hash = ? WHERE id = ?',
                      (hashed, admin_id))
    
    conn.commit()
    conn.close()

def create_password_reset_token(email: str) -> Optional[str]:
    """Create a password reset token for an admin user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    token = generate_reset_token()
    expires = datetime.now() + timedelta(hours=24)
    
    if USE_POSTGRES:
        cursor.execute('''
            UPDATE admin_users 
            SET password_reset_token = %s, password_reset_expires = %s
            WHERE email = %s
            RETURNING id
        ''', (token, expires, email))
        result = cursor.fetchone()
    else:
        cursor.execute('SELECT id FROM admin_users WHERE email = ?', (email,))
        result = cursor.fetchone()
        if result:
            cursor.execute('''
                UPDATE admin_users 
                SET password_reset_token = ?, password_reset_expires = ?
                WHERE email = ?
            ''', (token, expires, email))
    
    conn.commit()
    conn.close()
    
    return token if result else None

def verify_reset_token(token: str) -> Optional[dict]:
    """Verify a password reset token and return admin info if valid"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT id, email, username
            FROM admin_users 
            WHERE password_reset_token = %s AND password_reset_expires > %s
        ''', (token, datetime.now()))
        row = cursor.fetchone()
        if row:
            result = {'id': row[0], 'email': row[1], 'username': row[2]}
        else:
            result = None
    else:
        cursor.execute('''
            SELECT id, email, username
            FROM admin_users 
            WHERE password_reset_token = ? AND password_reset_expires > ?
        ''', (token, datetime.now()))
        result = cursor.fetchone()
    
    conn.close()
    return result

def reset_password_with_token(token: str, new_password: str) -> bool:
    """Reset password using a valid token"""
    admin = verify_reset_token(token)
    if not admin:
        return False
    
    conn = get_connection()
    cursor = conn.cursor()
    
    hashed = hash_password(new_password)
    
    if USE_POSTGRES:
        cursor.execute('''
            UPDATE admin_users 
            SET password_hash = %s, password_reset_token = NULL, password_reset_expires = NULL
            WHERE id = %s
        ''', (hashed, admin['id']))
    else:
        cursor.execute('''
            UPDATE admin_users 
            SET password_hash = ?, password_reset_token = NULL, password_reset_expires = NULL
            WHERE id = ?
        ''', (hashed, admin['id']))
    
    conn.commit()
    conn.close()
    return True

def create_coop(name: str, slug: str) -> int:
    """Create a new co-op"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            INSERT INTO coops (name, slug) VALUES (%s, %s) RETURNING id
        ''', (name, slug))
        coop_id = cursor.fetchone()[0]
    else:
        cursor.execute('''
            INSERT INTO coops (name, slug) VALUES (?, ?)
        ''', (name, slug))
        coop_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return coop_id

def get_coop_by_slug(slug: str):
    """Get co-op details by slug"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT id, name, slug, next_member_number, membership_agreement,
                   contact_email, send_member_emails, member_email_subject, member_email_body,
                   mailchimp_api_key, mailchimp_audience_id, stripe_account_id, created_at
            FROM coops WHERE slug = %s
        ''', (slug,))
        row = cursor.fetchone()
        if row:
            result = {
                'id': row[0],
                'name': row[1],
                'slug': row[2],
                'next_member_number': row[3],
                'membership_agreement': row[4],
                'contact_email': row[5],
                'send_member_emails': row[6],
                'member_email_subject': row[7],
                'member_email_body': row[8],
                'mailchimp_api_key': row[9],
                'mailchimp_audience_id': row[10],
                'stripe_account_id': row[11],
                'created_at': row[12]
            }
        else:
            result = None
    else:
        cursor.execute('SELECT * FROM coops WHERE slug = ?', (slug,))
        result = cursor.fetchone()

    conn.close()
    return result

def get_coop_by_id(coop_id: int):
    """Get co-op details by id"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT id, name, slug, next_member_number, membership_agreement,
                   contact_email, send_member_emails, member_email_subject, member_email_body,
                   mailchimp_api_key, mailchimp_audience_id, stripe_account_id, created_at
            FROM coops WHERE id = %s
        ''', (coop_id,))
        row = cursor.fetchone()
        if row:
            result = {
                'id': row[0],
                'name': row[1],
                'slug': row[2],
                'next_member_number': row[3],
                'membership_agreement': row[4],
                'contact_email': row[5],
                'send_member_emails': row[6],
                'member_email_subject': row[7],
                'member_email_body': row[8],
                'mailchimp_api_key': row[9],
                'mailchimp_audience_id': row[10],
                'stripe_account_id': row[11],
                'created_at': row[12]
            }
        else:
            result = None
    else:
        cursor.execute('SELECT * FROM coops WHERE id = ?', (coop_id,))
        result = cursor.fetchone()

    conn.close()
    return result

def update_membership_agreement(coop_id: int, agreement_text: str):
    """Update membership agreement for a co-op"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('UPDATE coops SET membership_agreement = %s WHERE id = %s',
                      (agreement_text, coop_id))
    else:
        cursor.execute('UPDATE coops SET membership_agreement = ? WHERE id = ?',
                      (agreement_text, coop_id))
    
    conn.commit()
    conn.close()

def update_coop_email_settings(coop_id: int, contact_email: Optional[str],
                               send_member_emails: bool,
                               member_email_subject: Optional[str],
                               member_email_body: Optional[str],
                               mailchimp_api_key: Optional[str] = None,
                               mailchimp_audience_id: Optional[str] = None):
    """Update email settings for a co-op"""
    conn = get_connection()
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute('''
            UPDATE coops SET contact_email = %s, send_member_emails = %s,
                member_email_subject = %s, member_email_body = %s,
                mailchimp_api_key = %s, mailchimp_audience_id = %s
            WHERE id = %s
        ''', (contact_email or None, send_member_emails,
              member_email_subject or None, member_email_body or None,
              mailchimp_api_key or None, mailchimp_audience_id or None, coop_id))
    else:
        cursor.execute('''
            UPDATE coops SET contact_email = ?, send_member_emails = ?,
                member_email_subject = ?, member_email_body = ?,
                mailchimp_api_key = ?, mailchimp_audience_id = ?
            WHERE id = ?
        ''', (contact_email or None, 1 if send_member_emails else 0,
              member_email_subject or None, member_email_body or None,
              mailchimp_api_key or None, mailchimp_audience_id or None, coop_id))

    conn.commit()
    conn.close()


def update_member(member_id: int, coop_id: int, first_name: str, last_name: str,
                  email: str, phone: str, address: str, city: str, state: str,
                  zip_code: str, payment_plan: str, membership_type_id: int) -> bool:
    """Update a member's details (scoped to coop for safety)"""
    conn = get_connection()
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute('''
            UPDATE members SET first_name = %s, last_name = %s, email = %s, phone = %s,
                address = %s, city = %s, state = %s, zip = %s,
                payment_plan = %s, membership_type_id = %s
            WHERE id = %s AND coop_id = %s
        ''', (first_name, last_name, email, phone, address, city, state, zip_code,
              payment_plan, membership_type_id, member_id, coop_id))
    else:
        cursor.execute('''
            UPDATE members SET first_name = ?, last_name = ?, email = ?, phone = ?,
                address = ?, city = ?, state = ?, zip = ?,
                payment_plan = ?, membership_type_id = ?
            WHERE id = ? AND coop_id = ?
        ''', (first_name, last_name, email, phone, address, city, state, zip_code,
              payment_plan, membership_type_id, member_id, coop_id))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_system_setting(key: str) -> Optional[str]:
    """Get a system setting value by key"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute('SELECT value FROM system_settings WHERE key = %s', (key,))
        row = cursor.fetchone()
        result = row[0] if row else None
    else:
        cursor.execute('SELECT value FROM system_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        result = row['value'] if row else None

    conn.close()
    return result


def update_system_setting(key: str, value: Optional[str]):
    """Set a system setting value (upsert)"""
    conn = get_connection()
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute('''
            INSERT INTO system_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        ''', (key, value or None))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)
        ''', (key, value or None))

    conn.commit()
    conn.close()


def create_membership_type(coop_id: int, name: str, equity_amount: float, 
                          dues_amount: float = 0, signup_fee: float = 0,
                          allows_installments: bool = True, installment_count: int = 4):
    """Create a membership type for a specific co-op"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            INSERT INTO membership_types 
            (coop_id, name, equity_amount, dues_amount, signup_fee, allows_installments, installment_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (coop_id, name, equity_amount, dues_amount, signup_fee, allows_installments, installment_count))
        type_id = cursor.fetchone()[0]
    else:
        cursor.execute('''
            INSERT INTO membership_types 
            (coop_id, name, equity_amount, dues_amount, signup_fee, allows_installments, installment_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (coop_id, name, equity_amount, dues_amount, signup_fee, 
              1 if allows_installments else 0, installment_count))
        type_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return type_id

def get_membership_types(coop_id: int):
    """Get all membership types for a co-op"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT id, name, equity_amount, dues_amount, signup_fee, 
                   allows_installments, installment_count
            FROM membership_types WHERE coop_id = %s
            ORDER BY equity_amount
        ''', (coop_id,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'name': row[1],
                'equity_amount': float(row[2]),
                'dues_amount': float(row[3]),
                'signup_fee': float(row[4]),
                'allows_installments': row[5],
                'installment_count': row[6]
            })
    else:
        cursor.execute('''
            SELECT id, name, equity_amount, dues_amount, signup_fee, 
                   allows_installments, installment_count
            FROM membership_types WHERE coop_id = ?
            ORDER BY equity_amount
        ''', (coop_id,))
        results = cursor.fetchall()
    
    conn.close()
    return results

def update_membership_type(type_id: int, coop_id: int, name: str, equity_amount: float,
                           dues_amount: float = 0, signup_fee: float = 0,
                           allows_installments: bool = True, installment_count: int = 4):
    """Update a membership type (scoped to the given co-op for safety)"""
    conn = get_connection()
    cursor = conn.cursor()

    if USE_POSTGRES:
        cursor.execute('''
            UPDATE membership_types
            SET name = %s, equity_amount = %s, dues_amount = %s, signup_fee = %s,
                allows_installments = %s, installment_count = %s
            WHERE id = %s AND coop_id = %s
        ''', (name, equity_amount, dues_amount, signup_fee,
              allows_installments, installment_count, type_id, coop_id))
    else:
        cursor.execute('''
            UPDATE membership_types
            SET name = ?, equity_amount = ?, dues_amount = ?, signup_fee = ?,
                allows_installments = ?, installment_count = ?
            WHERE id = ? AND coop_id = ?
        ''', (name, equity_amount, dues_amount, signup_fee,
              1 if allows_installments else 0, installment_count, type_id, coop_id))

    conn.commit()
    conn.close()

def delete_membership_type(type_id: int, coop_id: int):
    """Delete a membership type (with co-op ownership verification)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('DELETE FROM membership_types WHERE id = %s AND coop_id = %s',
                      (type_id, coop_id))
    else:
        cursor.execute('DELETE FROM membership_types WHERE id = ? AND coop_id = ?',
                      (type_id, coop_id))
    
    conn.commit()
    conn.close()

def create_member(coop_id: int, membership_type_id: int, first_name: str,
                 last_name: str, email: str, phone: str, address: str,
                 city: str, state: str, zip_code: str, payment_plan: str,
                 agreed_to_terms: bool = True, newsletter: bool = True,
                 stripe_payment_id: Optional[str] = None,
                 equity_paid: float = 0,
                 payment_date=None):
    """Create a new member and return member info"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get membership type details
    if USE_POSTGRES:
        cursor.execute('''
            SELECT equity_amount, dues_amount, signup_fee, installment_count
            FROM membership_types WHERE id = %s
        ''', (membership_type_id,))
    else:
        cursor.execute('''
            SELECT equity_amount, dues_amount, signup_fee, installment_count
            FROM membership_types WHERE id = ?
        ''', (membership_type_id,))
    
    type_info = cursor.fetchone()
    if not type_info:
        conn.close()
        raise ValueError("Invalid membership type")
    
    equity_amount = type_info[0]
    dues_amount = type_info[1]
    signup_fee = type_info[2]
    installment_count = type_info[3]
    
    # Get and increment member number
    if USE_POSTGRES:
        cursor.execute('''
            UPDATE coops SET next_member_number = next_member_number + 1 
            WHERE id = %s RETURNING next_member_number - 1
        ''', (coop_id,))
        member_number = cursor.fetchone()[0]
    else:
        cursor.execute('SELECT next_member_number FROM coops WHERE id = ?', (coop_id,))
        member_number = cursor.fetchone()[0]
        cursor.execute('UPDATE coops SET next_member_number = ? WHERE id = ?',
                      (member_number + 1, coop_id))
    
    # Create member
    if USE_POSTGRES:
        cursor.execute('''
            INSERT INTO members
            (coop_id, membership_type_id, member_number, first_name, last_name,
             email, phone, address, city, state, zip, payment_plan,
             total_equity, total_dues, signup_fee, agreed_to_terms, newsletter,
             stripe_payment_id, equity_paid, payment_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (coop_id, membership_type_id, member_number, first_name, last_name,
              email, phone, address, city, state, zip_code, payment_plan,
              equity_amount, dues_amount, signup_fee, agreed_to_terms, newsletter,
              stripe_payment_id, equity_paid, payment_date))
        member_id = cursor.fetchone()[0]
    else:
        cursor.execute('''
            INSERT INTO members
            (coop_id, membership_type_id, member_number, first_name, last_name,
             email, phone, address, city, state, zip, payment_plan,
             total_equity, total_dues, signup_fee, agreed_to_terms, newsletter,
             stripe_payment_id, equity_paid, payment_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (coop_id, membership_type_id, member_number, first_name, last_name,
              email, phone, address, city, state, zip_code, payment_plan,
              equity_amount, dues_amount, signup_fee,
              1 if agreed_to_terms else 0,
              1 if newsletter else 0,
              stripe_payment_id, equity_paid, payment_date))
        member_id = cursor.lastrowid
    
    # Create payment schedule if installments
    if payment_plan == 'installments':
        total_amount = equity_amount + signup_fee
        installment_amount = total_amount / installment_count
        
        for i in range(installment_count):
            due_date = datetime.now() + timedelta(days=90 * i)
            
            if USE_POSTGRES:
                cursor.execute('''
                    INSERT INTO payment_schedules (member_id, installment_number, due_date, amount)
                    VALUES (%s, %s, %s, %s)
                ''', (member_id, i + 1, due_date.date(), installment_amount))
            else:
                cursor.execute('''
                    INSERT INTO payment_schedules (member_id, installment_number, due_date, amount)
                    VALUES (?, ?, ?, ?)
                ''', (member_id, i + 1, due_date.date(), installment_amount))
    
    conn.commit()
    conn.close()
    
    return {
        'member_id': member_id,
        'member_number': member_number,
        'equity_amount': equity_amount,
        'dues_amount': dues_amount,
        'signup_fee': signup_fee
    }

def get_all_members(coop_id: int):
    """Get all members for a co-op with their membership type info"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('''
            SELECT m.id, m.coop_id, m.membership_type_id, m.member_number,
                   m.first_name, m.last_name, m.email, m.phone, m.address,
                   m.city, m.state, m.zip, m.payment_plan,
                   m.total_equity, m.total_dues, m.signup_fee,
                   m.agreed_to_terms, m.newsletter, m.signed_up_at,
                   mt.name as membership_type_name,
                   m.stripe_payment_id, m.equity_paid, m.payment_date
            FROM members m
            JOIN membership_types mt ON m.membership_type_id = mt.id
            WHERE m.coop_id = %s
            ORDER BY m.member_number
        ''', (coop_id,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'coop_id': row[1],
                'membership_type_id': row[2],
                'member_number': row[3],
                'first_name': row[4],
                'last_name': row[5],
                'email': row[6],
                'phone': row[7],
                'address': row[8],
                'city': row[9],
                'state': row[10],
                'zip': row[11],
                'payment_plan': row[12],
                'total_equity': row[13],
                'total_dues': row[14],
                'signup_fee': row[15],
                'agreed_to_terms': row[16],
                'newsletter': row[17],
                'signed_up_at': row[18],
                'membership_type_name': row[19],
                'stripe_payment_id': row[20],
                'equity_paid': row[21],
                'payment_date': row[22],
            })
    else:
        cursor.execute('''
            SELECT m.id, m.coop_id, m.membership_type_id, m.member_number,
                   m.first_name, m.last_name, m.email, m.phone, m.address,
                   m.city, m.state, m.zip, m.payment_plan,
                   m.total_equity, m.total_dues, m.signup_fee,
                   m.agreed_to_terms, m.newsletter, m.signed_up_at,
                   mt.name as membership_type_name
            FROM members m
            JOIN membership_types mt ON m.membership_type_id = mt.id
            WHERE m.coop_id = ?
            ORDER BY m.member_number
        ''', (coop_id,))
        results = cursor.fetchall()
    
    conn.close()
    return results

def delete_member(member_id: int, coop_id: int) -> bool:
    """Delete a single member (scoped to the given co-op for safety).
    
    Payment schedules cascade-delete via foreign key. Returns True if
    a row was deleted, False if no matching member existed.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('DELETE FROM members WHERE id = %s AND coop_id = %s',
                      (member_id, coop_id))
    else:
        cursor.execute('DELETE FROM members WHERE id = ? AND coop_id = ?',
                      (member_id, coop_id))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def update_coop_stripe_account(coop_id: int, stripe_account_id: Optional[str]):
    """Set or clear the Stripe Connect account ID for a co-op"""
    conn = get_connection()
    cursor = conn.cursor()
    if USE_POSTGRES:
        cursor.execute('UPDATE coops SET stripe_account_id = %s WHERE id = %s',
                       (stripe_account_id, coop_id))
    else:
        cursor.execute('UPDATE coops SET stripe_account_id = ? WHERE id = ?',
                       (stripe_account_id, coop_id))
    conn.commit()
    conn.close()


def delete_coop_cascade(coop_id: int) -> bool:
    """Delete a co-op and let foreign-key CASCADE remove all related rows.
    
    Relies on ON DELETE CASCADE declared on membership_types.coop_id,
    members.coop_id, admin_users.coop_id, and payment_schedules.member_id.
    Returns True if a co-op was deleted.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('DELETE FROM coops WHERE id = %s', (coop_id,))
    else:
        # SQLite needs foreign_keys=ON pragma for CASCADE to work
        cursor.execute('PRAGMA foreign_keys = ON')
        cursor.execute('DELETE FROM coops WHERE id = ?', (coop_id,))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_all_coops():
    """Get all co-ops for superadmin"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if USE_POSTGRES:
        cursor.execute('SELECT id, name, slug FROM coops ORDER BY name')
        rows = cursor.fetchall()
        results = [{'id': r[0], 'name': r[1], 'slug': r[2]} for r in rows]
    else:
        cursor.execute('SELECT id, name, slug FROM coops ORDER BY name')
        results = cursor.fetchall()
    
    conn.close()
    return results

def get_admin_users(coop_id: Optional[int] = None):
    """Get all admin users, optionally filtered by co-op"""
    conn = get_connection()
    if not USE_POSTGRES:
        conn.row_factory = dict_factory
    cursor = conn.cursor()
    
    if coop_id:
        if USE_POSTGRES:
            cursor.execute('''
                SELECT au.id, au.username, au.email, au.password_hash, au.coop_id, 
                       au.is_superadmin, au.password_reset_token, au.password_reset_expires, 
                       c.name as coop_name
                FROM admin_users au
                LEFT JOIN coops c ON au.coop_id = c.id
                WHERE au.coop_id = %s AND au.is_superadmin = FALSE
                ORDER BY au.username
            ''', (coop_id,))
        else:
            cursor.execute('''
                SELECT au.id, au.username, au.email, au.password_hash, au.coop_id, 
                       au.is_superadmin, au.password_reset_token, au.password_reset_expires, 
                       c.name as coop_name
                FROM admin_users au
                LEFT JOIN coops c ON au.coop_id = c.id
                WHERE au.coop_id = ? AND au.is_superadmin = 0
                ORDER BY au.username
            ''', (coop_id,))
    else:
        if USE_POSTGRES:
            cursor.execute('''
                SELECT au.id, au.username, au.email, au.password_hash, au.coop_id, 
                       au.is_superadmin, au.password_reset_token, au.password_reset_expires, 
                       c.name as coop_name
                FROM admin_users au
                LEFT JOIN coops c ON au.coop_id = c.id
                WHERE au.is_superadmin = FALSE
                ORDER BY au.username
            ''', ())
        else:
            cursor.execute('''
                SELECT au.id, au.username, au.email, au.password_hash, au.coop_id, 
                       au.is_superadmin, au.password_reset_token, au.password_reset_expires, 
                       c.name as coop_name
                FROM admin_users au
                LEFT JOIN coops c ON au.coop_id = c.id
                WHERE au.is_superadmin = 0
                ORDER BY au.username
            ''', ())
    
    if USE_POSTGRES:
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'password_hash': row[3],
                'coop_id': row[4],
                'is_superadmin': row[5],
                'password_reset_token': row[6],
                'password_reset_expires': row[7],
                'coop_name': row[8] if len(row) > 8 else None
            })
    else:
        results = cursor.fetchall()
    
    conn.close()
    return results
