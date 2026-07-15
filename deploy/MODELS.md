# Cloning Models — Chatterbox Variants

The service loads exactly **one** Chatterbox model at startup, selected by the
`CHATTERBOX_VARIANT` env var (see `app/engine.py`). All variants are
**zero-shot voice cloners**: a "cloned voice" is just a 5–10 s reference clip
stored in the private `voice-samples` bucket and read at synthesis time. There
is **no per-voice model, no training, no redeploy** — adding a voice (built-in
or user clone) never changes the model.

Verified against the upstream Resemble AI Chatterbox repo (2026-07).

## Variants (`CHATTERBOX_VARIANT`)

| Variant | Class loaded | Params | Languages | VRAM | Strengths |
|---|---|---|---|---|---|
| `turbo` **(default, DECIDED)** | `chatterbox.tts_turbo.ChatterboxTurboTTS` | 350M | English | ~6–8 GB | Lowest latency and compute — the speech-token-to-mel decoder is distilled from 10 steps to **1**. Native paralinguistic tags: `[laugh]`, `[chuckle]`, `[cough]`, etc. Built for production voice agents; excels at narration. |
| `original` | `chatterbox.tts.ChatterboxTTS` | 500M | English | ~8 GB | Creative controls: `exaggeration` (emotion intensity) and `cfg_weight` (pacing) tuning — both already exposed on the `/tts` request body. |
| `multilingual` | `chatterbox.mtl_tts.ChatterboxMultilingualTTS` | 500M | 23+ | ~8–10 GB | Multilingual V3: improved speaker similarity, reduced hallucination, cross-language voice cloning. |

Model weights download from Hugging Face on first startup into the `hfcache`
Docker volume (a few GB per variant); restarts reuse the cache.

### Multilingual language list

Arabic (ar), Danish (da), German (de), Greek (el), English (en), Spanish (es),
Finnish (fi), French (fr), Hebrew (he), Hindi (hi), Italian (it),
Japanese (ja), Korean (ko), Malay (ms), Dutch (nl), Norwegian (no),
Polish (pl), Portuguese (pt), Russian (ru), Swedish (sv), Swahili (sw),
Turkish (tr), Chinese (zh).

Upstream also ships a **Single Language Pack** (dedicated 500M finetunes for
zh, es-MX/latam, pt-BR, es-ES, pt-PT, hi). The service does not currently load
these — adding one would be a small `app/engine.py` change if a
dialect-sensitive market becomes a priority.

## Tuning knobs (per `/tts` request)

- `exaggeration` (default `0.5`) — emotion intensity. `~0.7+` for dramatic
  speech; higher values speed speech up.
- `cfg_weight` (default `0.5`) — pacing/adherence. Lower (`~0.3`) for slower,
  more deliberate delivery or fast-speaking reference clips; `0` when the
  reference clip's language differs from the target language (multilingual).

Defaults work well for most prompts.

## Reference clips (what a "voice" is)

- 5–10 seconds of clean, mono speech (WAV/WebM).
- Built-in voices: objects under `voice-samples/builtin/` — the file name
  becomes the display name (`warm-female.wav` → "Warm Female").
- User clones: the clip the user uploads via `/clone`; its storage path *is*
  the `voice_id`, registered in `voice_profiles`.
- Voice count has **zero** effect on GPU sizing.

## Watermark

Every output embeds Resemble's **Perth neural watermark** — imperceptible,
survives MP3 compression and editing, ~100% detection accuracy. Good for
provenance of AI-generated audio; extractable with the `perth` Python package.
Policy sign-off is an open question in `MONDAY-HANDOFF.md`.

## Sizing note

On the decided `AL40S.192GB` box (L40S, 48 GB VRAM), any single variant uses
under a quarter of the VRAM. Headroom options: multiple synthesis workers,
loading a second variant side by side (would need a small engine change), or
co-hosting future sovereignty AI workloads.
