import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

WINDOW_SECONDS = 300   # 5-minute sliding window
MAX_ATTEMPTS = 10      # attempts before lockout

_attempts: Dict[str, List[datetime]] = defaultdict(list)
_lock = asyncio.Lock()


async def is_rate_limited(key: str) -> bool:
    """Read-only check — does not record an attempt."""
    cutoff = datetime.utcnow() - timedelta(seconds=WINDOW_SECONDS)
    async with _lock:
        recent = [t for t in _attempts.get(key, []) if t > cutoff]
        return len(recent) >= MAX_ATTEMPTS


async def record_attempt(key: str):
    """Record one attempt, pruning entries outside the window."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    async with _lock:
        _attempts[key] = [t for t in _attempts.get(key, []) if t > cutoff]
        _attempts[key].append(now)


async def clear_attempts(key: str):
    """Reset attempts for a key (call on successful login)."""
    async with _lock:
        _attempts.pop(key, None)
