# Atlantic.net GPU Server — Requirements & Provisioning Reference

Single source of truth for provisioning the box that runs the City Center
Voice Service. Sizing was decided by James on 2026-07-11 (see
`MONDAY-HANDOFF.md` §Decisions); this doc consolidates it into one
provisioning checklist.

## 1. Server plan (DECIDED)

| Item | Value |
|---|---|
| Provider | Atlantic.net (sanctioned host for sovereignty-sensitive workloads, v8 §3.6) |
| Plan | **`AL40S.192GB`** — smallest GPU tier they sell |
| GPU | 1× NVIDIA **L40S**, 48 GB VRAM |
| CPU / RAM | 32 vCPU / 192 GB RAM |
| Disk | 1.4 TB NVMe |
| Price | ~$1,121/mo month-to-month (≈ $1.67/hr) |
| Term | **Month-to-month.** Do NOT take the 3-year term (~5.5% saving, $1,058.70/mo) until usage proves out. |
| OS | **Ubuntu 22.04 LTS** |

Why this plan: it is the entry GPU tier (no smaller GPU instance exists).
Chatterbox Turbo needs only ~6–8 GB VRAM, so the L40S's 48 GB buys concurrent
synthesis workers, the multilingual variant, and room to co-host future
sovereignty AI workloads on the same box. Voice count does **not** affect
sizing — built-in voices and user clones are just reference clips read at
synthesis time (zero-shot).

## 2. Resource budget

| Resource | Need | Headroom on AL40S.192GB |
|---|---|---|
| VRAM | Turbo ~6–8 GB; multilingual ~8–10 GB | 48 GB — room for several workers / a second variant |
| Disk | Docker image ~10 GB + HF model weights ~2–4 GB per variant + audio cache | 1.4 TB NVMe — ample |
| Network | Audio responses are small (MP3, seconds long) | any |

Model weights download from Hugging Face on **first container startup**
(warmup) into the `hfcache` Docker volume — first boot takes a few minutes;
restarts reuse the volume and are fast.

## 3. Network & firewall

- Inbound **443** (HTTPS) — open to the world; terminated by Caddy.
- Inbound **80** — open (Caddy needs it for the ACME HTTP challenge /
  HTTPS redirect).
- Inbound **22** (SSH) — restrict to admin IPs if the portal allows.
- Port **8000** (the app) — **never** exposed publicly. The container binds
  `127.0.0.1:8000` only; UFW additionally denies external 8000.

## 4. DNS

Point `voice.lifedailyos.app` (an **A record**) at the server's public IP
**before** starting Caddy, so the automatic Let's Encrypt certificate
issuance succeeds.

## 5. Software stack (installed by `01-provision.sh`)

1. NVIDIA driver (`ubuntu-drivers autoinstall`) — requires one reboot.
2. Docker Engine.
3. NVIDIA Container Toolkit (so `docker run --gpus all` works).
4. Caddy (automatic HTTPS reverse proxy).
5. UFW rules per §3.

## 6. Provisioning runbook

```bash
# In the Atlantic.net cloud portal: create the GPU Cloud Server
#   (AL40S.192GB, Ubuntu 22.04 LTS), then SSH in as root/sudo user.

git clone https://github.com/JMAC3303/chatterbox-voice-service.git
cd chatterbox-voice-service

# Phase 1 — drivers (reboots the box at the end)
sudo bash deploy/01-provision.sh

# ... after the reboot, SSH back in:
cd chatterbox-voice-service
sudo bash deploy/01-provision.sh     # re-run; it is idempotent and continues

# Phase 2 — configure env, then deploy
cp .env.example .env                 # fill in the two Supabase secrets
                                     # (see deploy/ENV-CHECKLIST.md)
sudo bash deploy/02-deploy.sh

# Phase 3 — smoke test
bash deploy/smoke-test.sh https://voice.lifedailyos.app
```

## 7. Compliance (before go-live)

- [ ] Server + model listed in the ISMS asset inventory (S16c) and risk
      register (S16b).
- [ ] `voice-samples` / `creed-audio-cache` buckets confirmed **private**
      (biometric data, GDPR Article 9).
- [ ] Secrets set via env only; rotation documented (S9/§9.4).
- [ ] RTO/RPO defined (S28) — the service is stateless apart from cache;
      redeploy = recovery.
- [ ] GitHub repo set to **private** (it is currently public — flagged
      2026-07-15).
