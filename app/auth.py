"""Supabase JWT validation.

Every request must carry the caller's Supabase access token as a Bearer token.
We verify it locally with the project's JWT secret (HS256), mirroring the
ai-proxy trust model: the shared City Center SSO issues the token, and any
ecosystem app authenticated against the same project can call this service.
"""
from __future__ import annotations

import jwt
from fastapi import Depends, Header, HTTPException, status

from .config import get_settings


class AuthedUser:
    def __init__(self, user_id: str, email: str | None, claims: dict):
        self.user_id = user_id
        self.email = email
        self.claims = claims


def require_user(authorization: str | None = Header(default=None)) -> AuthedUser:
    settings = get_settings()

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()

    if not settings.SUPABASE_JWT_SECRET:
        # Fail closed — never accept unverifiable tokens.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is not configured on the server",
        )

    try:
        claims = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject",
        )

    return AuthedUser(user_id=user_id, email=claims.get("email"), claims=claims)


UserDep = Depends(require_user)
