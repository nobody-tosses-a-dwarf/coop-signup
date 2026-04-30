import os
from typing import Optional
import aiohttp

SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL', 'noreply@coopsignup.com')
BASE_DOMAIN = os.getenv('BASE_DOMAIN', 'coopsignup.com')

DEFAULT_MEMBER_SUBJECT = "Welcome to {coop_name}!"

DEFAULT_MEMBER_BODY = """\
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #2c5f2d;">Welcome to {coop_name}!</h2>

    <p>Dear {first_name},</p>

    <p>Thank you for becoming a member of {coop_name}. We're excited to have you as part of our co-op community!</p>

    <h3>Your Membership Details:</h3>
    <p>
        <strong>Member Number:</strong> {member_number}<br>
        <strong>Membership Type:</strong> {membership_type}<br>
        <strong>Total:</strong> ${total_amount}<br>
        <strong>Payment Plan:</strong> {payment_plan_label}
    </p>

    <h3>Your Contact Information on File:</h3>
    <p>
        <strong>Name:</strong> {first_name} {last_name}<br>
        <strong>Email:</strong> {email}<br>
        <strong>Phone:</strong> {phone}<br>
        <strong>Address:</strong> {address}, {city}, {state} {zip}
    </p>

    <p>{payment_note}</p>

    <p>If you have any questions, please don't hesitate to reach out to us.</p>

    <p>Welcome aboard!</p>

    <p style="margin-top: 30px;"><strong>The {coop_name} Team</strong></p>

    <p style="color: #666; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
        This is an automated confirmation from the Co-op Signup System.
    </p>
</body>
</html>"""

DEFAULT_ADMIN_SUBJECT = "Welcome to {coop_name} - Co-op Signup System"

DEFAULT_ADMIN_BODY = """\
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2 style="color: #2c5f2d;">Welcome to the Co-op Signup System!</h2>

    <p>You've been added as an administrator for <strong>{coop_name}</strong>.</p>

    <h3>Your Login Credentials:</h3>
    <p>
        <strong>Login URL:</strong> <a href="{login_url}">{login_url}</a><br>
        <strong>Username:</strong> {email}<br>
        <strong>Temporary Password:</strong> <code style="background: #f4f4f4; padding: 2px 6px; border-radius: 3px;">{temp_password}</code>
    </p>

    <p style="background: #fff3cd; padding: 12px; border-left: 4px solid #ffc107; margin: 20px 0;">
        <strong>Important:</strong> Please change your password immediately after logging in for the first time.
    </p>

    <h3>What You Can Do:</h3>
    <ul>
        <li>Manage membership types for your co-op</li>
        <li>View and export member signups</li>
        <li>Create custom membership agreements</li>
        <li>Generate QR codes and embed codes for your signup form</li>
    </ul>

    <p>If you have any questions or need assistance, please contact your system administrator.</p>

    <p style="color: #666; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
        This is an automated message from the Co-op Signup System.
    </p>
</body>
</html>"""


def apply_placeholders(template: str, variables: dict) -> str:
    """Replace {placeholder} variables in a template string."""
    for key, value in variables.items():
        template = template.replace('{' + key + '}', str(value) if value is not None else '')
    return template


async def send_email(to_email: str, subject: str, html_content: str,
                     reply_to: Optional[str] = None) -> bool:
    """Send email via SendGrid API"""
    if not SENDGRID_API_KEY:
        print("WARNING: SENDGRID_API_KEY not set - email not sent")
        print(f"Would have sent to {to_email}: {subject}")
        return False

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_content}]
    }

    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 202:
                    return True
                else:
                    error_text = await response.text()
                    print(f"SendGrid error: {response.status} - {error_text}")
                    return False
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False


async def send_admin_welcome_email(email: str, coop_name: str, temp_password: str,
                                   custom_subject: Optional[str] = None,
                                   custom_body: Optional[str] = None):
    """Send welcome email to new co-op admin with temporary password"""
    variables = {
        'email': email,
        'coop_name': coop_name,
        'temp_password': temp_password,
        'login_url': f"https://{BASE_DOMAIN}/login",
    }

    subject = apply_placeholders(custom_subject or DEFAULT_ADMIN_SUBJECT, variables)
    html_content = apply_placeholders(custom_body or DEFAULT_ADMIN_BODY, variables)

    return await send_email(email, subject, html_content)


async def send_password_reset_email(email: str, reset_token: str):
    """Send password reset email with reset link"""
    reset_url = f"https://{BASE_DOMAIN}/reset-password?token={reset_token}"
    subject = "Password Reset Request - Co-op Signup System"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #2c5f2d;">Password Reset Request</h2>

        <p>We received a request to reset your password for the Co-op Signup System.</p>

        <p>Click the link below to reset your password:</p>

        <p style="margin: 25px 0;">
            <a href="{reset_url}" style="background: #2c5f2d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                Reset Password
            </a>
        </p>

        <p>Or copy and paste this URL into your browser:</p>
        <p style="background: #f4f4f4; padding: 10px; border-radius: 3px; word-break: break-all;">
            {reset_url}
        </p>

        <p style="background: #fff3cd; padding: 12px; border-left: 4px solid #ffc107; margin: 20px 0;">
            <strong>This link will expire in 24 hours.</strong>
        </p>

        <p>If you didn't request this password reset, you can safely ignore this email.</p>

        <p style="color: #666; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
            This is an automated message from the Co-op Signup System.
        </p>
    </body>
    </html>
    """

    return await send_email(email, subject, html_content)


async def send_member_confirmation_email(email: str, coop_name: str, member_number: int,
                                         first_name: str, membership_type: str,
                                         total_amount: float, payment_plan: str,
                                         last_name: str = '',
                                         phone: str = '',
                                         address: str = '',
                                         city: str = '',
                                         state: str = '',
                                         zip_code: str = '',
                                         reply_to: Optional[str] = None,
                                         custom_subject: Optional[str] = None,
                                         custom_body: Optional[str] = None):
    """Send confirmation email to new member after signup"""
    payment_plan_labels = {
        'full': 'Paid in Full',
        'installments': 'Quarterly Installments',
        'later': 'Pay Later'
    }

    payment_notes = {
        'full': 'Your equity has been paid in full — no further payments are required. We look forward to seeing you at the co-op!',
        'installments': 'Your first installment payment has been processed. The co-op will be in touch regarding your remaining payments.',
        'later': 'You have chosen to arrange payment with the co-op directly. Please reach out to them at your earliest convenience to complete your equity payment.',
    }

    variables = {
        'first_name': first_name,
        'coop_name': coop_name,
        'member_number': str(member_number),
        'membership_type': membership_type,
        'total_amount': f'{total_amount:.2f}',
        'payment_plan': payment_plan,
        'payment_plan_label': payment_plan_labels.get(payment_plan, payment_plan),
        'payment_note': payment_notes.get(payment_plan, ''),
        'last_name': last_name,
        'phone': phone,
        'address': address,
        'city': city,
        'state': state,
        'zip': zip_code,
    }

    subject = apply_placeholders(custom_subject or DEFAULT_MEMBER_SUBJECT, variables)
    html_content = apply_placeholders(custom_body or DEFAULT_MEMBER_BODY, variables)

    return await send_email(email, subject, html_content, reply_to=reply_to)
