import re

# US States for validation
US_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_phone(phone: str) -> bool:
    """Validate phone number (allows various formats)"""
    # Remove common separators
    cleaned = re.sub(r'[\s\-\(\)\.]+', '', phone)
    # Should be 10 or 11 digits (with optional country code)
    return bool(re.match(r'^\d{10,11}$', cleaned))

def validate_zip(zip_code: str) -> bool:
    """Validate ZIP code (5 digits or 5+4 format)"""
    pattern = r'^\d{5}(-\d{4})?$'
    return bool(re.match(pattern, zip_code))

def validate_slug(slug: str) -> bool:
    """Validate slug format (lowercase letters, numbers, hyphens only)"""
    pattern = r'^[a-z0-9-]+$'
    return bool(re.match(pattern, slug))

def format_phone(phone: str) -> str:
    """Format phone number consistently"""
    cleaned = re.sub(r'[\s\-\(\)\.]+', '', phone)
    if len(cleaned) == 10:
        return f"({cleaned[:3]}) {cleaned[3:6]}-{cleaned[6:]}"
    elif len(cleaned) == 11 and cleaned[0] == '1':
        return f"({cleaned[1:4]}) {cleaned[4:7]}-{cleaned[7:]}"
    return phone
