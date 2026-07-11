# MONDAY-HANDOFF — City Center Voice Service (Chatterbox)

**Repo:** `chatterbox-voice-service` · **Prepared:** 2026-07-11
**For:** full-stack dev + infra, standing up the ecosystem voice capability

One service, used across the **entire LDOS tech stack** (PrayerLIFE, Speak LIFE,
LifeDNA creeds, Music LIFE, …) for text-to-speech + zero-shot voice cloning.
Replaces per-app ElevenLabs (too expensive). Open-source Chatterbox (Resemble
AI, MIT), self-hosted on our Atlantic.net GPU box.

---

## ⚠️ CRITICAL — READ FIRST

- **Shared DB.** Uses the City Center Supabase project `tsnbktwryvnbmgsvzxdt`
  (same as every ecosystem app). Apply `migrations/0001_voice_service.sql`
  centrally. It only adds voice tables — safe — but review before running.
- **Buckets must be PRIVATE.** `voice-samples` (biometric — Article 9) and
  `creed-audio-cache` must not be public. The service uses signed URLs +
  service-role reads. Confirm before go-live.
- **Needs a GPU.** Chatterbox requires an NVIDIA GPU for usable latency. This
  cannot run on a standard CPU VM at production speed.

---

## ORDER OF OPERATIONS

1. **Apply DB migration** `migrations/0001_voice_service.sql` to the shared
   project → creates `voice_profiles`, `voice_usage`, `voice_service_config`
   (seeds one config row). Adjust the `is_platform_admin()` predicate to the
   ecosystem's real admin check.
2. **Confirm bucket privacy** for `voice-samples` and `creed-audio-cache`.
3. **Provision the Atlantic.net GPU server** and deploy per `README.md`
   (NVIDIA driver + container toolkit → `docker build` → `docker run --gpus all`
   → Caddy/nginx TLS at `voice.lifedailyos.app`). Set env from `.env.example`:
   `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`,
   `CHATTERBOX_VARIANT`, `ALLOWED_ORIGINS`.
4. **Point the apps at it.** Set `VITE_VOICE_PROXY_URL=https://voice.lifedailyos.app`
   in each app (PrayerLIFE already reads it and sends `X-Client-App: prayer-life`).
5. **Wire the Admin-CMS "Voice Service" page** (see below) — an independent
   session owns this; coordinate the schema it reads (`voice_usage` /
   `voice_service_config`).

---

## TESTED / NOT TESTED

| Item | State |
|---|---|
| Service code (FastAPI, auth, engine, storage, usage logging, config gate) | ✅ authored, reviewed |
| Runtime / model load / synthesis | ❌ NOT run here — no local GPU/Python. First real test is on the Atlantic box (`GET /healthz`, then a `/tts`). |
| Migration SQL | ✅ authored; ⚠️ review `is_platform_admin()` + journals/PK assumptions before applying |
| App client contract | ✅ PrayerLIFE `voiceService.ts` matches `/tts` + `/clone` and sends `X-Client-App` |

**First smoke test on the box:** `curl $HOST/healthz` → `{"status":"ok"}`; then a
signed-in `/tts` with a short text and a default voice; confirm a `voice_usage`
row appears.

---

## ADMIN-CMS INTEGRATION (owned by the spun-off session)

The service is instrumented so the LDOS Admin-CMS can **manage it and track
usage without redeploys**:
- **Usage dashboard** — read `voice_usage` (per-app, cache-hit ratio, latency,
  volume over time) via the CMS service-role backend.
- **Controls** — edit `voice_service_config` row: `maintenance_mode`,
  `enabled_apps`, `max_tts_chars`, `default_variant`, `daily_char_budget_per_user`,
  `atlantic_endpoint`. The service reads this on every call.
- **Health** — poll `GET /healthz` on the Atlantic endpoint for status.

Target repo: `LIFE-OS-CMS-Admin-Panel-jul26-` (add a "Voice Service" page under
`src/pages/`). This is a separate workstream — see the spawned session.

---

## OPEN QUESTIONS FOR A HUMAN
- **Atlantic GPU sizing** — Turbo (350M) fits ~6–8 GB VRAM; pick the instance
  tier and confirm budget.
- **Default voices** — ship a small set of built-in voice samples (paths in
  `voice-samples`) for apps that don't clone, or require every voice to be
  user-cloned? Affects onboarding.
- **Watermark policy** — Chatterbox embeds Resemble's Perth neural watermark on
  all output. Confirm that's acceptable for all use cases (it's a plus for
  provenance, but note it).

## REFERENCE
- Service + Atlantic hosting: `README.md`
- Schema: `migrations/0001_voice_service.sql`
- App client example: `../Prayer-Faith-LIFE-jan26-/src/lib/voiceService.ts`
