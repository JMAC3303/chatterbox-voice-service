# MONDAY-HANDOFF — City Center Voice Service (Chatterbox)

**Repo:** `chatterbox-voice-service` · **Prepared:** 2026-07-11 · **Updated:** 2026-07-11 (eve)
**For:** full-stack dev + infra, standing up the ecosystem voice capability

> **STATUS UPDATE (2026-07-11):** The Admin-CMS "Voice Service" page is BUILT
> (see §Admin-CMS below). Atlantic deployment is NOT done — it needs
> Atlantic.net portal + shared-DB credentials that only James/infra hold.
> The migration was hardened (branch `feature/deploy-prep`): it now creates
> `public.is_platform_admin()` itself when the shared DB doesn't have one yet
> (Music LIFE Daily phase-1 and Speak LIFE bucket-2 also define theirs —
> whichever migration lands first wins; review that the surviving definition
> is acceptable for ALL of them. Music LIFE's includes church_admin/editors;
> this repo's fallback is super_admin-only).

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

## ADMIN-CMS INTEGRATION — ✅ BUILT (2026-07-11)

Done in `LIFE-OS-CMS-Admin-Panel-jul26-` on branch `feature/voice-service-page`
(unpushed, unmerged — see that repo's `MONDAY-HANDOFF.md` for run steps):
- **Usage dashboard** — `voice_usage` read via the CMS service-role backend
  (`server/voice-service-routes.ts`, mounted at `/api/voice`): per-app volume +
  cache-hit + latency, daily chart, top users, 7d/30d/90d ranges.
- **Controls** — edits the single `voice_service_config` row (all six fields);
  the service reads it on every call, so changes apply without redeploy.
- **Health** — CMS backend probes `GET {atlantic_endpoint}/healthz`; badge
  polls every 60s.

Prereqs for it to light up: apply this repo's migration to the shared DB and
set `SUPABASE_SERVICE_ROLE_KEY` in the CMS server env. Everything degrades
with explicit error messages until then (tested).

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
