"""Supabase Storage + DB helpers (server-side, service role).

Voice samples and generated creed audio are GDPR Article 9 / biometric data.
Buckets MUST be private; we return short-lived signed URLs, never public URLs.
"""
from __future__ import annotations

import httpx

from .config import get_settings


def _headers() -> dict:
    settings = get_settings()
    return {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    }


async def upload_audio(bucket: str, path: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={**_headers(), "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
        resp.raise_for_status()


async def signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{bucket}/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=_headers(), json={"expiresIn": expires_in})
        resp.raise_for_status()
        signed = resp.json().get("signedURL", "")
    return f"{settings.SUPABASE_URL}/storage/v1{signed}"


async def download_object(bucket: str, path: str) -> bytes | None:
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=_headers())
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content


async def set_user_voice_id(user_id: str, voice_id: str) -> None:
    """Persist the cloned voice id on the user's LIFE DNA profile."""
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/rest/v1/user_life_dna_profiles"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            url,
            headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
            params={"user_id": f"eq.{user_id}"},
            json={"voice_id": voice_id},
        )
        resp.raise_for_status()


async def log_usage(row: dict) -> None:
    """Append a row to voice_usage (best-effort — never fails the request)."""
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/rest/v1/voice_usage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={**_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
                json=row,
            )
            resp.raise_for_status()
    except Exception:
        # Usage logging must never break synthesis.
        pass


async def get_service_config() -> dict:
    """Read the single voice_service_config row (Admin-CMS managed)."""
    settings = get_settings()
    url = f"{settings.SUPABASE_URL}/rest/v1/voice_service_config"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url, headers=_headers(), params={"id": "eq.1", "select": "*"}
            )
            resp.raise_for_status()
            rows = resp.json()
            return rows[0] if rows else {}
    except Exception:
        return {}
