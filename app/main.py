"""City Center Voice Service (Chatterbox).

A single ecosystem service that every LIFE Daily OS app calls for text-to-speech
and zero-shot voice cloning. Replaces per-app ElevenLabs usage (LDOS v8 S3/S13):
providers/keys live here, apps call with the user's Supabase JWT.

Endpoints (match the apps' voiceService client):
  POST /tts    { text, voice_id, user_id? }        -> audio/mpeg
  POST /clone  { user_id, voice_sample_url, voice_name } -> { voice_id }
  GET  /healthz
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import time

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import AuthedUser, require_user
from .config import get_settings
from . import engine, storage

app = FastAPI(title="City Center Voice Service", version="1.0.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
def _startup() -> None:
    # Load the model once so the first request isn't cold.
    engine.warmup()


class TtsRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    user_id: str | None = None
    exaggeration: float = 0.5
    cfg_weight: float = 0.5


class CloneRequest(BaseModel):
    user_id: str
    voice_sample_url: str
    voice_name: str = "My LIFEdna Voice"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "variant": settings.CHATTERBOX_VARIANT}


# Built-in default voices are curated reference clips seeded (by ops) under
# this prefix in the private voice-samples bucket. Zero-shot synthesis reads
# them exactly like a user's cloned sample, so "adding a voice" is just
# uploading a 5–10s licensed clip — no model change, no redeploy.
BUILTIN_VOICE_PREFIX = "builtin/"


@app.get("/voices")
async def voices(user: AuthedUser = Depends(require_user)) -> dict:
    """Voices the caller may synthesize with: the built-in set + their own."""
    builtin: list[dict] = []
    try:
        objects = await storage.list_objects(
            settings.VOICE_SAMPLES_BUCKET, BUILTIN_VOICE_PREFIX
        )
        for obj in objects:
            name = obj.get("name", "")
            # Skip folder placeholders / hidden objects.
            if not name or name.startswith("."):
                continue
            stem = name.rsplit(".", 1)[0]
            builtin.append({
                "voice_id": f"{BUILTIN_VOICE_PREFIX}{name}",
                "name": stem.replace("-", " ").replace("_", " ").title(),
                "builtin": True,
            })
    except Exception:
        pass  # bucket not seeded yet — return whatever else we have

    mine = [
        {
            "voice_id": p.get("voice_id"),
            "name": p.get("display_name") or "My Voice",
            "builtin": False,
            "app": p.get("app"),
        }
        for p in await storage.get_user_voice_profiles(user.user_id)
    ]
    return {"voices": builtin + mine}


def _cache_path(text: str, voice_id: str, user_id: str | None) -> str:
    digest = hashlib.sha256(f"{voice_id}::{text}".encode()).hexdigest()
    filename = f"{digest}.mp3"
    return f"{user_id}/{filename}" if user_id else filename


async def _enforce_config(app_name: str | None) -> dict:
    """Apply Admin-CMS-managed config: maintenance mode + per-app enablement."""
    config = await storage.get_service_config()
    if config.get("maintenance_mode"):
        raise HTTPException(status_code=503, detail="Voice service is in maintenance mode")
    enabled = config.get("enabled_apps")
    if enabled and app_name and app_name not in enabled:
        raise HTTPException(status_code=403, detail=f"Voice service not enabled for '{app_name}'")
    return config


@app.post("/tts")
async def tts(
    req: TtsRequest,
    user: AuthedUser = Depends(require_user),
    x_client_app: str | None = Header(default=None),
) -> Response:
    config = await _enforce_config(x_client_app)
    max_chars = int(config.get("max_tts_chars") or settings.MAX_TTS_CHARS)
    if len(req.text) > max_chars:
        raise HTTPException(status_code=413, detail="Text too long")

    # A user may only synthesize under their own namespace.
    owner = req.user_id or user.user_id
    if owner != user.user_id:
        raise HTTPException(status_code=403, detail="Cannot synthesize for another user")

    started = time.monotonic()
    storage_path = _cache_path(req.text, req.voice_id, owner)

    # Serve from cache if present.
    cached = await storage.download_object(settings.AUDIO_CACHE_BUCKET, storage_path)
    if cached is not None:
        await storage.log_usage({
            "user_id": user.user_id,
            "app": x_client_app,
            "operation": "tts",
            "characters": len(req.text),
            "cache_hit": True,
            "model_variant": settings.CHATTERBOX_VARIANT,
            "latency_ms": int((time.monotonic() - started) * 1000),
        })
        return Response(content=cached, media_type="audio/mpeg", headers={"X-Cache": "hit"})

    # A voice_id here is a stored reference-sample path in the voice-samples
    # bucket (zero-shot cloning uses the reference clip at synthesis time).
    ref_path = None
    tmp = None
    try:
        sample = await storage.download_object(settings.VOICE_SAMPLES_BUCKET, req.voice_id)
        if sample is not None:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(sample)
            tmp.flush()
            ref_path = tmp.name

        mp3_bytes, _sr = engine.synthesize(
            req.text,
            reference_audio_path=ref_path,
            exaggeration=req.exaggeration,
            cfg_weight=req.cfg_weight,
        )
    finally:
        if tmp is not None:
            tmp.close()
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # Cache for next time (private bucket).
    await storage.upload_audio(settings.AUDIO_CACHE_BUCKET, storage_path, mp3_bytes, "audio/mpeg")

    await storage.log_usage({
        "user_id": user.user_id,
        "app": x_client_app,
        "operation": "tts",
        "characters": len(req.text),
        "cache_hit": False,
        "model_variant": settings.CHATTERBOX_VARIANT,
        "latency_ms": int((time.monotonic() - started) * 1000),
    })

    return Response(content=mp3_bytes, media_type="audio/mpeg", headers={"X-Cache": "miss"})


@app.post("/clone")
async def clone(
    req: CloneRequest,
    user: AuthedUser = Depends(require_user),
    x_client_app: str | None = Header(default=None),
) -> dict:
    if req.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Cannot clone for another user")
    await _enforce_config(x_client_app)

    # Chatterbox is zero-shot: "cloning" means registering the user's reference
    # sample as their voice id. The sample path IS the voice id; synthesis reads
    # it from the private voice-samples bucket at generation time. No third-party
    # voice registry, no biometric data leaving our infrastructure (v8 S13).
    #
    # voice_sample_url is a signed URL to the just-uploaded sample. We derive the
    # storage path so future TTS can load it server-side.
    sample_path = _extract_storage_path(req.voice_sample_url, settings.VOICE_SAMPLES_BUCKET)
    if not sample_path:
        raise HTTPException(status_code=400, detail="Could not resolve voice sample path")

    # Validate the sample is reachable and reasonable.
    async with httpx.AsyncClient(timeout=60) as client:
        head = await client.get(req.voice_sample_url)
        if head.status_code >= 400:
            raise HTTPException(status_code=400, detail="Voice sample not accessible")

    voice_id = sample_path  # the private path within voice-samples
    await storage.set_user_voice_id(req.user_id, voice_id)
    await storage.register_voice_profile(
        req.user_id, voice_id, req.voice_name, x_client_app
    )
    await storage.log_usage({
        "user_id": user.user_id,
        "app": x_client_app,
        "operation": "clone",
        "characters": 0,
        "cache_hit": False,
        "model_variant": settings.CHATTERBOX_VARIANT,
    })
    return {"voice_id": voice_id}


def _extract_storage_path(url: str, bucket: str) -> str | None:
    """Pull the object path out of a Supabase storage URL for `bucket`."""
    marker = f"/{bucket}/"
    idx = url.find(marker)
    if idx == -1:
        return None
    path = url[idx + len(marker):]
    # Strip any query string (signed URLs carry a token).
    return path.split("?", 1)[0] or None
