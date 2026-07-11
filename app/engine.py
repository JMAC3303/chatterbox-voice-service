"""Chatterbox TTS engine wrapper.

Loads the model once at startup and serves synthesis + zero-shot voice cloning.
Chatterbox (Resemble AI, MIT) embeds Resemble's Perth neural watermark in every
output, which is desirable for provenance of AI-generated audio.
"""
from __future__ import annotations

import io
import threading

import torch
import torchaudio as ta

from .config import get_settings

_model = None
_lock = threading.Lock()


def _load_model():
    settings = get_settings()
    variant = settings.CHATTERBOX_VARIANT.lower()
    device = settings.DEVICE

    if variant == "original":
        from chatterbox.tts import ChatterboxTTS

        return ChatterboxTTS.from_pretrained(device=device)
    if variant == "multilingual":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        return ChatterboxMultilingualTTS.from_pretrained(device=device)
    # default: turbo (low-latency, paralinguistic tags)
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    return ChatterboxTurboTTS.from_pretrained(device=device)


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = _load_model()
    return _model


def warmup() -> None:
    """Load the model at startup so the first request isn't cold."""
    get_model()


def _wav_to_mp3_bytes(wav: "torch.Tensor", sample_rate: int) -> bytes:
    """Encode a waveform tensor to MP3 bytes."""
    buffer = io.BytesIO()
    # torchaudio uses the sox/ffmpeg backend for MP3 encoding.
    ta.save(buffer, wav.cpu(), sample_rate, format="mp3")
    return buffer.getvalue()


def synthesize(text: str, reference_audio_path: str | None = None,
               exaggeration: float = 0.5, cfg_weight: float = 0.5) -> tuple[bytes, int]:
    """Generate speech. If reference_audio_path is given, clone that voice
    (zero-shot). Returns (mp3_bytes, sample_rate).
    """
    model = get_model()
    # Serialize generation — a single GPU model instance is not thread-safe.
    with _lock:
        if reference_audio_path:
            wav = model.generate(
                text,
                audio_prompt_path=reference_audio_path,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
            )
        else:
            wav = model.generate(text, exaggeration=exaggeration, cfg_weight=cfg_weight)
        sr = model.sr
    return _wav_to_mp3_bytes(wav, sr), sr
