"""Shared slowapi rate limiter instance."""

from slowapi import Limiter
from starlette.requests import Request


def _get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "unknown"


limiter = Limiter(key_func=_get_real_ip)
