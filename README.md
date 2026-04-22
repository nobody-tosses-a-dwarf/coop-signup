# Co-op Membership Signup System

A web-based membership signup system designed for food co-ops. Collects member
information, validates it, assigns member numbers, tracks payment plans, and
exports directly to CoPOS-compatible tab-delimited format for POS import.

## Quick Start (Local Development)

### 1. Install Python 3.10+

If you don't have Python, download from https://www.python.org/downloads/

To check: open Terminal (Mac) or Command Prompt (Windows) and type:
```
python3 --version
```

### 2. Download this project

Put the `coop-signup` folder somewhere on your computer (Desktop is fine).

### 3. Install dependencies

Open Terminal, navigate to the project folder, and run:
```
cd ~/Desktop/coop-signup
pip3 install -r requirements.txt
```

### 4. Start the server

```
python3 app.py
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Open in your browser

- **Signup form:** http://localhost:8000/chatham
- **Admin dashboard:** http://localhost:8000/admin/chatham
- **CoPOS export:** http://localhost:8000/admin/chatham/export
- **Co-op directory:** http://localhost:8000/

## Project Structure

```
coop-signup/
    app.py              # Main web application (routes and request handling)
    database.py         # Database models and member creation logic
    validation.py       # Input validation (phone, email, zip, address)
    copos_export.py     # CoPOS 60-column tab-delimited export generator
    requirements.txt    # Python package dependencies
    templates/          # HTML templates (what users see)
        home.html       # Co-op directory page
        signup.html     # Member signup form
        confirmation.html  # Post-signup confirmation
        admin.html      # Admin dashboard
    static/             # CSS, images (currently minimal)
```

## How It Works

### For Members
1. Visit the signup URL (e.g., yoursite.com/chatham)
2. Fill in name, address, phone, email
3. Choose membership type (Household $100 or Business $500)
4. Choose payment plan (Full, Quarterly Installments, or Pay Later)
5. Get assigned a member number immediately

### For Admins
1. Visit /admin/chatham to see all members
2. View payment plan status for each member
3. Click "Export for CoPOS" to download the import file
4. Import the .TXT file directly into CoPOS

### CoPOS Export
The export generates a tab-delimited TXT file with all 60 columns matching the
CoPOS Member Import template exactly. Save as MEMBERS#.TXT and import per CoPOS
instructions.

## Adding a New Co-op

Currently done by adding entries to the database. In a future version, this will
have an admin UI. For now, edit the `seed_chatham()` function in database.py as
a template for adding new co-ops.

## Deployment (Production)

For production deployment (making it accessible on the internet):

### Option A: Railway (Recommended for simplicity)
1. Create account at https://railway.app
2. Connect your GitHub repo
3. Railway auto-detects Python and deploys
4. Add a PostgreSQL database from Railway's dashboard
5. Set DATABASE_URL environment variable

### Option B: DigitalOcean VPS
1. Create a $6/mo droplet (Ubuntu 24.04)
2. SSH in, install Python, clone the project
3. Run behind nginx with a systemd service
4. Point your domain at the droplet's IP

### Database for Production
For production, switch from SQLite to PostgreSQL:
- Install psycopg2: `pip3 install psycopg2-binary`
- Set DATABASE_URL environment variable
- The database.py module will need a small update for PostgreSQL syntax

## Future Phases

- **Phase 2:** Stripe payment integration (collect payments at signup)
- **Phase 3:** Admin dashboard enhancements, multi-co-op management UI
- **Phase 4:** Embeddable widget for co-op websites, QR code generation
