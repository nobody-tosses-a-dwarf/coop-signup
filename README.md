# Co-op Membership Signup System - Version 2.0

## What's New in Version 2.0

### Major Features Added

#### 1. **Per-Co-op Membership Type Management**
- Individual co-ops now manage their own membership types (previously managed by superadmin)
- Co-op admins can create, view, and delete membership types from their admin dashboard
- Each membership type is linked to a specific co-op

#### 2. **Membership Agreement System**
- Co-ops can create custom membership agreements
- Signup form includes required checkbox to agree to membership agreement
- Agreement displays on a separate, printable page (`/[slug]/membership-agreement`)
- Co-op admins can edit agreement text via expandable form in their dashboard

#### 3. **Email-Based Admin System**
- All admin accounts now use email as username (simplifies login)
- When superadmin creates a co-op admin:
  - System generates secure random temporary password
  - Sends welcome email with login credentials via SendGrid
  - No password field needed in superadmin interface
- Admin users receive professional welcome emails with setup instructions

#### 4. **Password Management**
- **Change Password**: Logged-in admins can change their password via `/change-password`
- **Forgot Password**: Public reset request form at `/forgot-password`
- **Password Reset**: Time-limited reset tokens (24-hour expiration) sent via email
- Password reset flow: request → email with token link → new password form → success

#### 5. **Email Confirmations**
- New members receive confirmation emails after signup
- Email includes member number, membership type, and payment plan
- Formatted HTML emails with co-op branding

#### 6. **Reorganized Admin UI**
- Membership Types section now at top of admin dashboard
- Member List in the middle
- Embed & Share section moved below member list (expandable)
- Membership Agreement editor added at bottom (expandable)

### Technical Changes

#### New Dependencies
- `aiohttp==3.11.10` - For async SendGrid API calls

#### New Environment Variables Required
```bash
SENDGRID_API_KEY=your_sendgrid_api_key_here
FROM_EMAIL=noreply@coopsignup.com
```

#### Database Schema Changes
```sql
-- Admin users table updated
ALTER TABLE admin_users ADD COLUMN email TEXT NOT NULL UNIQUE;
ALTER TABLE admin_users ADD COLUMN password_reset_token TEXT;
ALTER TABLE admin_users ADD COLUMN password_reset_expires TIMESTAMP;

-- Membership types now linked to co-ops
ALTER TABLE membership_types ADD COLUMN coop_id INTEGER NOT NULL REFERENCES coops(id);

-- Co-ops table updated
ALTER TABLE coops ADD COLUMN membership_agreement TEXT;

-- Members table updated
ALTER TABLE members ADD COLUMN agreed_to_terms BOOLEAN DEFAULT FALSE;
```

#### New Routes
- `GET /forgot-password` - Password reset request form
- `POST /forgot-password` - Process reset request, send email
- `GET /reset-password?token=...` - Password reset form
- `POST /reset-password` - Process password reset
- `GET /change-password` - Change password form (authenticated)
- `POST /change-password` - Process password change
- `GET /{slug}/membership-agreement` - View membership agreement
- `POST /{slug}/admin/membership-types/create` - Create membership type
- `POST /{slug}/admin/membership-types/{id}/delete` - Delete membership type
- `POST /{slug}/admin/update-agreement` - Update membership agreement

#### New Files
- `email.py` - SendGrid email integration module
- `templates/membership_agreement.html` - Agreement display page
- `templates/forgot_password.html` - Password reset request
- `templates/reset_password.html` - Password reset form
- `templates/change_password.html` - Change password form

## Setup Instructions

### 1. SendGrid Configuration

1. **Create SendGrid Account** (Free tier: 100 emails/day)
   - Sign up at https://sendgrid.com/
   - Verify your sender email address or domain

2. **Get API Key**
   - Go to Settings → API Keys
   - Create new API key with "Full Access"
   - Copy the key immediately (won't be shown again)

3. **Add to Render Environment Variables**
   ```
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxx
   FROM_EMAIL=noreply@coopsignup.com
   ```

### 2. Database Migration

The database schema will auto-update when you deploy, but you may need to:

1. **Update existing admin users with emails**
   ```sql
   UPDATE admin_users 
   SET email = username || '@temp.com' 
   WHERE email IS NULL;
   ```

2. **Link existing membership types to co-ops** (if any exist)
   ```sql
   -- This assumes you only have one co-op
   UPDATE membership_types 
   SET coop_id = (SELECT id FROM coops LIMIT 1)
   WHERE coop_id IS NULL;
   ```

### 3. Deployment Workflow (Unchanged)

```bash
# In your local coop-signup directory
cp [downloaded files] .
git add .
git commit -m "Update to v2.0: per-coop member types, membership agreement, email system"
git push
```

Render will auto-deploy on push.

## Usage Guide for Co-op Admins

### Managing Membership Types

1. Log in to your co-op admin dashboard
2. At the top, you'll see your existing membership types
3. Click "Add New Membership Type" to expand the form
4. Fill in:
   - **Membership Name** (e.g., "Household", "Business")
   - **Equity Amount** (the ownership share amount)
   - **Annual Dues** (optional, usually $0 for equity model)
   - **Signup Fee** (optional)
   - **Allow installments** (checkbox)
   - **Number of installments** (default 4 for quarterly)
5. Click "Create Membership Type"
6. To delete a type, click the red "Delete" button (cannot be undone)

### Creating a Membership Agreement

1. Scroll to bottom of admin dashboard
2. In the "Membership Agreement" section, enter your agreement text
3. Click "Save Membership Agreement"
4. The agreement will now appear as a required checkbox on the signup form
5. Members can click the link to view/print the full agreement before signing up

### Password Management

**For first-time login (after receiving welcome email):**
1. Use the temporary password from your email
2. After logging in, click "Change Password" in the header
3. Enter your temporary password as "current password"
4. Choose a new secure password

**If you forget your password:**
1. Go to the login page
2. Click "Forgot your password?"
3. Enter your email address
4. Check your email for a reset link (expires in 24 hours)
5. Click the link and set a new password

## Usage Guide for Superadmins

### Creating a New Co-op

1. Log in to superadmin dashboard
2. In "Create New Co-op" section:
   - Enter co-op name (e.g., "Chatham Real Food Market Co-op")
   - Enter URL slug (lowercase, hyphens only, e.g., "chatham")
3. Click "Create Co-op"

### Creating a Co-op Admin

1. In "Create Co-op Admin User" section:
   - Enter the admin's email address
   - Select their co-op from dropdown
2. Click "Create Admin User"
3. System will:
   - Generate a secure temporary password
   - Send welcome email with login credentials
   - Admin will be prompted to change password on first login

**No password field needed** - the system handles it automatically!

## Email Templates

The system sends three types of emails:

### 1. Admin Welcome Email
- Sent when superadmin creates a co-op admin
- Includes temporary password and login link
- Reminds admin to change password immediately

### 2. Password Reset Email
- Sent when admin requests password reset
- Includes time-limited reset link (24 hours)
- Clearly marked as automated message

### 3. Member Confirmation Email
- Sent after successful member signup
- Includes member number, membership type, payment plan
- Welcome message from the co-op

## Troubleshooting

### Emails Not Sending

1. **Check SendGrid API Key**
   - Verify `SENDGRID_API_KEY` is set in Render environment variables
   - Check SendGrid dashboard for API key status

2. **Check FROM_EMAIL**
   - Must be verified in SendGrid (sender authentication)
   - For free tier, can only send from verified addresses

3. **Check Render Logs**
   ```bash
   # Look for email-related errors
   # Email module prints warnings if SENDGRID_API_KEY is missing
   ```

### Migration Issues

If you have existing data and encounter issues:

1. **Check PostgreSQL logs** in Render dashboard
2. **Verify columns exist**: Run SQL to inspect schema
3. **Manual fixes**: Use Render's built-in psql shell to run corrections

### Admin Login Issues

- Usernames are now email addresses
- Old usernames may not work - use the "Forgot Password" flow to reset

## Architecture Notes

### Email System
- Uses SendGrid API (not SMTP) for reliability
- Async email sending via aiohttp (non-blocking)
- HTML email templates with inline CSS
- Graceful failure: logs warning if SENDGRID_API_KEY missing

### Password Reset Security
- Tokens stored in database with expiration timestamp
- Tokens are cryptographically secure (secrets.token_urlsafe)
- 24-hour expiration enforced at database level
- Used tokens are cleared after successful reset

### Admin Authentication
- Email = username (simplifies UX)
- Passwords hashed with SHA-256
- Session cookies signed with itsdangerous
- 24-hour session expiration

## Render Configuration

**Current Environment Variables:**
```
DATABASE_URL=[PostgreSQL connection string]
ADMIN_PASSWORD=[Superadmin password]
SECRET_KEY=[Session encryption key]
BASE_DOMAIN=coopsignup.com
SENDGRID_API_KEY=[Your SendGrid API key]
FROM_EMAIL=noreply@coopsignup.com
```

**Recommended Next Steps:**
1. Upgrade to Render paid tier ($7/mo) to eliminate spindown before public launch
2. Set up custom domain DNS (already configured for coopsignup.com)
3. Enable Render's automatic SSL certificate

## Files Changed

**Updated:**
- `database.py` - Email fields, password reset, per-coop membership types
- `app.py` - All new routes and email integration
- `requirements.txt` - Added aiohttp
- `templates/signup.html` - Agreement checkbox
- `templates/admin.html` - Reorganized UI, membership type management
- `templates/superadmin.html` - Email-based admin creation

**New:**
- `email.py` - SendGrid integration
- `templates/membership_agreement.html`
- `templates/forgot_password.html`
- `templates/reset_password.html`
- `templates/change_password.html`

**Unchanged:**
- `copos_export.py` - Export logic unchanged
- `validation.py` - Input validation unchanged
- `templates/confirmation.html` - Unchanged
- `templates/home.html` - Unchanged
- `templates/login.html` - Minor text change ("Email Address" label)

## Testing Checklist

Before going live:

- [ ] SendGrid API key configured and working
- [ ] Test admin creation (verify welcome email arrives)
- [ ] Test password reset flow (request → email → reset → login)
- [ ] Test member signup with agreement checkbox
- [ ] Test membership type creation/deletion
- [ ] Test membership agreement editing
- [ ] Test CoPOS export still works correctly
- [ ] Test QR code and embed code generation
- [ ] Verify all emails render correctly on mobile

## Future Enhancements

Potential next steps:
- Stripe payment integration (collect payments at signup)
- Member portal (members can view/update their info)
- Email customization per co-op (custom branding, from address)
- Bulk email to members from admin dashboard
- Payment tracking and reminders for installment plans
