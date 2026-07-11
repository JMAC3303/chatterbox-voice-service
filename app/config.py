"""Configuration for the City Center voice service.

All secrets come from environment variables — never hardcode (LDOS v8 S9).
"""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    # --- Supabase (shared City Center project) ---
    # Used to validate the caller's JWT and to read/write voice rows + storage.
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    # JWT secret (Supabase project → Settings → API → JWT Secret) for local
    # verification of access tokens without a network round-trip.
    SUPABASE_JWT_SECRET: str = os.environ.get("SUPABASE_JWT_SECRET", "")
    # Service role key — used ONLY server-side for storage/db writes the user
    # is entitled to. Never exposed to clients.
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    # --- Model ---
    # "turbo" (350M, low latency), "original" (500M, creative controls),
    # or "multilingual" (500M, 23+ languages).
    CHATTERBOX_VARIANT: str = os.environ.get("CHATTERBOX_VARIANT", "turbo")
    DEVICE: str = os.environ.get("DEVICE", "cuda")  # "cuda" | "cpu" | "mps"

    # --- Service ---
    # Allowed CORS origins (comma-separated) — the app + ecosystem domains only.
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get("ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    # Max characters per TTS request (abuse protection, LDOS v8 S23).
    MAX_TTS_CHARS: int = int(os.environ.get("MAX_TTS_CHARS", "2000"))
    # Max reference-clip seconds for cloning.
    MAX_CLONE_SECONDS: int = int(os.environ.get("MAX_CLONE_SECONDS", "60"))

    # --- Storage buckets (private; signed URLs only) ---
    AUDIO_CACHE_BUCKET: str = os.environ.get("AUDIO_CACHE_BUCKET", "creed-audio-cache")
    VOICE_SAMPLES_BUCKET: str = os.environ.get("VOICE_SAMPLES_BUCKET", "voice-samples")


@lru_cache
def get_settings() -> Settings:
    return Settings()
