# Quick Deployment Guide - Co-op Signup v2.0

## What Changed

### For You (The Admin)
- **You now manage your own membership types** (no longer done by superadmin)
- **You can create a membership agreement** that members must agree to
- **Email-based login** (username = your email address)
- **Password reset** via email if you forget
- **Member confirmation emails** sent automatically after signup

### For Superadmins Creating New Co-ops
- When creating a co-op admin, just enter their **email** (no password)
- System generates temporary password and **emails it to them**
- They'll change it on first login

### UI Changes
- Membership Types section at top of your admin dashboard
- Embed & Share section moved below member list
- New Membership Agreement editor at bottom

## Deployment Steps

### 1. Download All Files
Download the complete `/mnt/user-data/outputs/` folder contents to your local `coop-signup` directory.

### 2. Add SendGrid Credentials to Render

**Before deploying, you need to set up SendGrid for sending emails.**

#### Get SendGrid API Key:
1. Go to https://sendgrid.com/ and sign up (free tier: 100 emails/day)
2. Verify your sender email address
3. Go to Settings → API Keys
4. Create new API key with "Full Access"
5. **Copy the key immediately** (you can't see it again!)

#### Add to Render:
1. Go to your Render dashboard
2. Click on your `coop-signup` web service
3. Go to "Environment" tab
4. Add these two new environment variables:
   ```
   SENDGRID_API_KEY=SG.your_actual_api_key_here
   FROM_EMAIL=noreply@coopsignup.com
   ```
5. Save changes (don't deploy yet)

### 3. Deploy to Render

```bash
cd %USERPROFILE%\Downloads\Co-op Signup\coop-signup
git add .
git commit -m "Update to v2.0: per-coop member types, membership agreement, email system"
git push
```

Render will auto-deploy. Watch the deploy log for any errors.

### 4. Verify Everything Works

After deployment:

1. **Test admin creation** (if you're a superadmin):
   - Create a test admin for your co-op
   - Verify welcome email arrives with temp password
   
2. **Test login**:
   - Log in with your email address
   - Change your password via the "Change Password" link
   
3. **Test membership types**:
   - Create a test membership type
   - View it on the signup page
   - Delete it (if needed)
   
4. **Test membership agreement**:
   - Add agreement text in admin dashboard
   - Check signup page - should show agreement checkbox
   - Click agreement link - should open printable page
   
5. **Test signup**:
   - Complete a test signup
   - Verify confirmation email arrives
   - Check member appears in admin dashboard
   
6. **Test CoPOS export**:
   - Export members to verify format still correct

## Important Notes

### Email Configuration
- If `SENDGRID_API_KEY` is not set, emails won't send (but everything else works)
- The system will log warnings about missing email config
- For testing, you can proceed without SendGrid (just no emails)

### Existing Data
- Your existing members and co-op data are **safe**
- Database will auto-migrate when you deploy
- If you have existing membership types, they'll need to be linked to your co-op (see README)

### First-Time Admin Users
If you created admin users before this update:
- They need to use the "Forgot Password" flow to reset via email
- Or you can recreate them through superadmin (which sends welcome email)

## What to Expect

### When You First Log In
1. Log in with your email address (username = email now)
2. You'll see the new UI layout:
   - Membership Types at top (initially empty if you haven't created any)
   - Your member list in the middle
   - Embed & Share below (collapsed)
   - Membership Agreement editor at bottom (collapsed)

### Creating Your First Membership Type
1. Click "Add New Membership Type" 
2. Fill in the form (example for Chatham):
   - Name: "Household Membership"
   - Equity Amount: 100.00
   - Dues: 0.00
   - Signup Fee: 0.00
   - Check "Allow installment payments"
   - Installments: 4
3. Click "Create Membership Type"
4. Repeat for other types (e.g., "Business Membership" at $500)

### Creating Your Membership Agreement
1. Scroll to "Membership Agreement" section
2. Click to expand
3. Paste your agreement text
4. Click "Save Membership Agreement"
5. Test the signup page - should now require checkbox

## Troubleshooting

### "No membership types configured"
- You need to create at least one membership type before members can sign up
- Click "Add New Membership Type" in your admin dashboard

### Emails not arriving
- Check Render environment variables include `SENDGRID_API_KEY`
- Verify SendGrid API key is active in SendGrid dashboard
- Check Render logs for email errors

### Can't log in with old username
- Usernames are now email addresses
- Use "Forgot Password" to reset via email
- Or ask superadmin to recreate your account

### Member signup requires agreement checkbox but I don't have an agreement
- Either create a membership agreement OR
- Clear the membership agreement field (save with empty text)
- Checkbox only appears if agreement text exists

## Files Included

**Python Files:**
- `app.py` - Main application with all routes
- `database.py` - Database operations
- `email.py` - **NEW** SendGrid email integration
- `copos_export.py` - CoPOS export (unchanged)
- `validation.py` - Input validation (unchanged)

**Templates:**
- `admin.html` - **UPDATED** Admin dashboard
- `superadmin.html` - **UPDATED** Superadmin interface
- `signup.html` - **UPDATED** Signup form with agreement checkbox
- `membership_agreement.html` - **NEW** Agreement display page
- `forgot_password.html` - **NEW** Password reset request
- `reset_password.html` - **NEW** Password reset form
- `change_password.html` - **NEW** Change password form
- `login.html`, `home.html`, `confirmation.html` - Minor updates

**Configuration:**
- `requirements.txt` - **UPDATED** Added aiohttp
- `.python-version` - Python 3.12.7
- `README.md` - **NEW** Complete documentation

## Questions?

Check the full README.md for:
- Detailed architecture notes
- Email template details
- Database migration specifics
- Future enhancement ideas

## Ready to Go Live?

Before public launch:
1. Upgrade Render to paid tier ($7/mo) to eliminate spindown
2. Test all features thoroughly
3. Create real membership types
4. Write your membership agreement
5. Share your signup link!

---

**Your signup URL:** https://coopsignup.com/chatham
**Your admin dashboard:** https://coopsignup.com/chatham/admin
