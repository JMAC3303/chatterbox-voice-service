# City Center Voice Service (Chatterbox)

The LIFE Daily OS ecosystem voice capability: **text-to-speech and zero-shot
voice cloning** for every app (PrayerLIFE, Speak LIFE, LifeDNA creeds, Music
LIFE, etc.), served from one place. It wraps [Resemble AI's Chatterbox](https://github.com/resemble-ai/chatterbox)
(open-source, MIT) and is hosted on our **Atlantic.net** GPU infrastructure.

This replaces per-app ElevenLabs usage. Per the v8 Master Tech Stack:
- **S3 (AI sovereignty):** apps never call a voice provider directly and never
  hold a voice-provider key. They call this service with the user's Supabase JWT.
- **S13 (data sovereignty):** voice samples (biometric, GDPR Article 9) and
  generated audio never leave our infrastructure and never train a third party's
  model. Chatterbox is self-hosted; weights are ours (MIT).
- **S9 (secrets):** all secrets are environment variables; nothing in source.
- **Atlantic.net** is the sanctioned host for sovereignty-sensitive workloads
  (§3.6) — this service is one such workload and must be listed in the asset
  inventory (S16c) and risk register (S16b).

Why Chatterbox over ElevenLabs: MIT license (no per-character cost, no royalties,
no usage caps), zero-shot cloning from a few seconds of audio, emotion/intensity
control, 23-language multilingual variant, and a built-in Perth neural watermark
on every output for provenance.

---

## API

All endpoints require `Authorization: Bearer <supabase_access_token>`.

### `POST /tts`
```json
{ "text": "Be still and know that I am God.", "voice_id": "<user-id>/<sample>.wav", "user_id": "<uuid>" }
```
Returns `audio/mpeg`. Identical (voice_id, text) pairs are cached in the private
`creed-audio-cache` bucket and served on repeat (`X-Cache: hit`). `voice_id` is
the private storage path of the user's reference sample; omit it (or pass a
built-in voice path) for a default voice.

### `POST /clone`
```json
{ "user_id": "<uuid>", "voice_sample_url": "<signed-url-to-voice-samples/...>", "voice_name": "My LIFEdna Voice" }
```
Returns `{ "voice_id": "<user-id>/<sample>.webm" }`. Because Chatterbox is
zero-shot, "cloning" registers the user's reference sample as their voice id and
persists it on `user_life_dna_profiles.voice_id`. Synthesis reads the sample
server-side at generation time — the biometric sample never goes to any third
party.

### `GET /voices`
Voices the signed-in caller may synthesize with: the curated **built-in set**
(objects under `builtin/` in the private `voice-samples` bucket) plus the
caller's own registered voices from `voice_profiles`. Returns
`{ "voices": [{ "voice_id", "name", "builtin" }] }`. Adding a built-in voice =
uploading a 5–10s reference clip to `voice-samples/builtin/` — zero-shot means
no model change and no redeploy.

### `GET /healthz`
Liveness + which model variant is loaded.

The request/response shapes match the apps' `voiceService.ts` client, which
targets `VITE_VOICE_PROXY_URL` (e.g. `https://voice.lifedailyos.app`).

---

## Hosting on Atlantic.net (GPU)

Chatterbox needs an NVIDIA GPU for acceptable latency (Turbo runs comfortably on
a single modern GPU; CPU works but is slow).

### 1. Provision a GPU cloud server
**Chosen plan (James, 2026-07-11): `AL40S.192GB`** — Atlantic.net's smallest
GPU tier (1× NVIDIA L40S 48 GB, 32 vCPU, 192 GB RAM, 1.4 TB NVMe;
~$1,121/mo month-to-month ≈ $1.67/hr). Rationale:
- It's the entry tier; there is no smaller GPU instance. The L40S's 48 GB VRAM
  is far above Turbo's ~6–8 GB need, which buys concurrent synthesis workers,
  the multilingual variant, and room to co-host future sovereignty AI
  workloads (v8 §3.6) on the same box.
- Voice count does NOT affect sizing — built-in voices and user clones are
  just reference clips read at synthesis time (zero-shot).
- Start **month-to-month**; the 3-year term only saves ~5.5% ($1,058.70/mo) —
  commit after usage proves out.

In the Atlantic.net cloud portal, create the **GPU Cloud Server**:
- **OS:** Ubuntu 22.04 LTS.
- Open inbound **443** (HTTPS via the reverse proxy below); keep **8000**
  (the app port) firewalled to localhost only.

### 2. Install NVIDIA driver + container toolkit
```bash
sudo apt-get update && sudo apt-get install -y ubuntu-drivers-common
sudo ubuntu-drivers autoinstall && sudo reboot
# after reboot, verify:
nvidia-smi
# Docker + NVIDIA Container Toolkit
curl -fsSL https://get.docker.com | sh
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
```

### 3. Deploy the service
```bash
git clone <this-repo> && cd chatterbox-voice-service
cp .env.example .env    # fill in SUPABASE_JWT_SECRET + SERVICE_ROLE_KEY
docker build -t voice-service .
docker run -d --name voice --gpus all --env-file .env \
  -p 127.0.0.1:8000:8000 \
  -v hfcache:/root/.cache/huggingface \
  --restart unless-stopped voice-service
```
The `hfcache` volume persists model weights so restarts don't re-download them.

### 4. TLS reverse proxy
Point DNS (`voice.lifedailyos.app`) at the server, then front port 8000 with
Caddy (automatic HTTPS) or nginx:
```
voice.lifedailyos.app {
    reverse_proxy 127.0.0.1:8000
}
```

### 5. Wire the apps
Set `VITE_VOICE_PROXY_URL=https://voice.lifedailyos.app` in each app's env.
No app holds any voice key — auth is the user's Supabase JWT.

---

## Usage tracking + Admin-CMS management

Every `/tts` and `/clone` call is logged (server-side, best-effort) to
`voice_usage` in the shared DB, attributed by the caller's `X-Client-App` header
(e.g. `prayer-life`, `speak-life`). This powers the **Voice Service** page in the
LDOS Admin-CMS panel: per-app usage, cache-hit ratio, latency, and cost tracking
across the whole tech stack.

The service reads a single-row `voice_service_config` table on each call, so the
Admin-CMS can manage the Atlantic deployment **without a redeploy**:
- `maintenance_mode` — flip the service off (returns 503).
- `enabled_apps` — allow-list which LDOS apps may call it.
- `max_tts_chars` — per-request character cap.
- `default_variant`, `daily_char_budget_per_user`, `atlantic_endpoint`.

Apply `migrations/0001_voice_service.sql` to the shared DB (`voice_profiles`,
`voice_usage`, `voice_service_config`) before first run.

## Prerequisites in Supabase (one-time)

- Apply `migrations/0001_voice_service.sql` (voice tables + config row).
- Make **`voice-samples`** and **`creed-audio-cache`** buckets **private** (no
  public URLs). This service uses signed URLs and service-role reads.
- **Seed the built-in voice set** (decision 2026-07-11: apps get default
  voices AND user cloning): upload 8–15 curated reference clips (5–10s each,
  mono WAV/WebM, varied gender/age/tone) to `voice-samples/builtin/`. File
  name becomes the display name (`warm-female.wav` → "Warm Female").
  ⚠️ Licensing: record in-house or use permissively licensed clips (e.g.
  CC-BY corpora like VCTK — keep attribution); never seed a real person's
  voice without written consent (biometric, Article 9).
- Ensure `user_life_dna_profiles` has a `voice_id text` column.
- The service verifies caller JWTs with the project **JWT secret** — same shared
  City Center project all apps authenticate against. Every app calling the
  service should send `X-Client-App: <app-slug>` for per-app usage attribution.

## Local development (CPU)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DEVICE=cpu CHATTERBOX_VARIANT=turbo
uvicorn app.main:app --reload
```

## Compliance / ops checklist
- [ ] Server + model listed in the ISMS asset inventory (S16c) and risk register (S16b).
- [ ] `voice-samples` / `creed-audio-cache` buckets confirmed private.
- [ ] JWT secret + service-role key set via env only; rotation documented (S9/§9.4).
- [ ] RTO/RPO defined for the service (S28); it is stateless apart from cache — redeploy = recovery.
- [ ] Rate limits / `MAX_TTS_CHARS` tuned per abuse-protection posture (S23).
