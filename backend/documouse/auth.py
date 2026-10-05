"""Shared-token authentication.

When DOCUMOUSE_AUTH_TOKEN is set, every /api/* request (except /api/health)
must carry an ``Authorization: Bearer <token>`` header whose value matches.
When the setting is empty the gate is wide open (local development).
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .config import get_settings


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Reject /api/* requests that don't carry the right bearer token."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Let CORS preflight through.
        if request.method == "OPTIONS":
            return await call_next(request)
        
        token = get_settings().auth_token
        # No token configured → open access (local dev).
        if not token:
            return await call_next(request)
        # Only gate /api/* paths (not docs, not static, etc.).
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        # /api/health is always public so monitoring can reach it.
        if path == "/api/health":
            return await call_next(request)
        # Check Authorization header.
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {token}":
            return await call_next(request)
        return Response("Unauthorized", status_code=401, media_type="text/plain")
