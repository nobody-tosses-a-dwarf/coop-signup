import hashlib
import aiohttp


async def subscribe_member(api_key: str, audience_id: str,
                           email: str, first_name: str, last_name: str) -> bool:
    """Subscribe a member to a Mailchimp audience.

    Uses PUT (upsert) so re-submitting an existing email is safe.
    status_if_new=subscribed means already-unsubscribed contacts are not
    forcibly re-added — their existing status is preserved.
    """
    server = api_key.split('-')[-1]
    subscriber_hash = hashlib.md5(email.strip().lower().encode()).hexdigest()
    url = f"https://{server}.api.mailchimp.com/3.0/lists/{audience_id}/members/{subscriber_hash}"

    payload = {
        "email_address": email,
        "status_if_new": "subscribed",
        "merge_fields": {
            "FNAME": first_name,
            "LNAME": last_name,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                json=payload,
                auth=aiohttp.BasicAuth("anystring", api_key),
            ) as response:
                if response.status in (200, 201):
                    return True
                error_text = await response.text()
                print(f"Mailchimp error: {response.status} - {error_text}")
                return False
    except Exception as e:
        print(f"Mailchimp subscription failed: {e}")
        return False
