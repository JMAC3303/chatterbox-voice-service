# Environment & Pre-Deploy Checklist

Everything that must be in place before `deploy/02-deploy.sh` runs on the
Atlantic box. Secrets are env-only — nothing goes in source (LDOS v8 S9).

## 1. `.env` on the server

`cp .env.example .env`, then fill in:

| Variable | Value / where to get it | Required |
|---|---|---|
| `SUPABASE_URL` | `https://tsnbktwryvnbmgsvzxdt.supabase.co` (already set in the example — the shared City Center project) | yes |
| `SUPABASE_JWT_SECRET` | Supabase dashboard → project `tsnbktwryvnbmgsvzxdt` → Settings → API → **JWT Secret**. Used to verify caller access tokens locally. | **yes — blank in example** |
| `SUPABASE_SERVICE_ROLE_KEY` | Same page → **service_role key**. Server-side only; never shipped to clients. | **yes — blank in example** |
| `CHATTERBOX_VARIANT` | `turbo` (default) \| `original` \| `multilingual` — see `deploy/MODELS.md` | defaulted |
| `DEVICE` | `cuda` on the Atlantic box | defaulted |
| `ALLOWED_ORIGINS` | Comma-separated app domains, e.g. `https://prayer.lifedailyos.app,https://app.deeplysmart.app`. Add each LDOS app domain that will call the service. | yes |
| `MAX_TTS_CHARS` | `2000` (also runtime-overridable via `voice_service_config.max_tts_chars`) | defaulted |
| `MAX_CLONE_SECONDS` | `60` | defaulted |
| `AUDIO_CACHE_BUCKET` | `creed-audio-cache` | defaulted |
| `VOICE_SAMPLES_BUCKET` | `voice-samples` | defaulted |

`02-deploy.sh` refuses to start if the two Supabase secrets are blank.

## 2. Shared DB (one-time, before first run)

Apply [`migrations/0001_voice_service.sql`](../migrations/0001_voice_service.sql)
to the shared City Center project (`tsnbktwryvnbmgsvzxdt`). It creates:

- `voice_profiles` — registered/cloned voices (RLS: owner only),
- `voice_usage` — append-only usage log (service-role writes only),
- `voice_service_config` — single Admin-CMS-managed config row (seeded).

Review first (per MONDAY-HANDOFF):

- The migration creates `public.is_platform_admin()` **only if it doesn't
  already exist**. Music LIFE Daily phase-1 and Speak LIFE bucket-2 also
  define one — whichever lands first wins. This repo's fallback is
  super_admin-only; Music LIFE's includes church_admin/editors. Confirm the
  surviving definition is acceptable for **all** consumers.
- Ensure `user_life_dna_profiles` has a `voice_id text` column (the `/clone`
  endpoint persists to it).

## 3. Storage buckets (one-time)

- [ ] `voice-samples` bucket exists and is **PRIVATE** (biometric samples —
      GDPR Article 9; no public URLs, signed URLs + service-role reads only).
- [ ] `creed-audio-cache` bucket exists and is **PRIVATE**.
- [ ] **Seed built-in voices**: upload 8–15 curated reference clips
      (5–10 s each, mono WAV/WebM, varied gender/age/tone) to
      `voice-samples/builtin/`. File name becomes the display name
      (`warm-female.wav` → "Warm Female").
      Licensing: record in-house or use permissively licensed clips (e.g.
      CC-BY corpora like VCTK — keep attribution). Never seed a real
      person's voice without written consent.

## 4. DNS / TLS

- [ ] `voice.lifedailyos.app` A record → Atlantic server public IP (before
      Caddy starts, so the Let's Encrypt issuance succeeds).

## 5. Wiring the apps (after deploy)

- [ ] Set `VITE_VOICE_PROXY_URL=https://voice.lifedailyos.app` in each LDOS
      app's env (PrayerLIFE already reads it and sends
      `X-Client-App: prayer-life`).
- [ ] Admin-CMS: set `SUPABASE_SERVICE_ROLE_KEY` in the CMS server env and
      set `voice_service_config.atlantic_endpoint` to the live URL so the
      health badge and dashboard light up.
- [ ] Allow-list each calling app in `voice_service_config.enabled_apps`
      (defaults to `{prayer-life}`).

## 6. Verification

Run `bash deploy/smoke-test.sh https://voice.lifedailyos.app`:

1. `/healthz` returns `{"status":"ok","variant":"turbo"}`.
2. With `SUPABASE_ACCESS_TOKEN` set: `/voices` lists the built-in set, and a
   short `/tts` returns playable MP3 bytes.
3. Confirm a `voice_usage` row appeared in the shared DB.
