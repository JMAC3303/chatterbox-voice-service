#!/usr/bin/env bash
# Build and run the voice service container on the Atlantic.net GPU server.
#
# Idempotent: rebuilds the image and replaces the running container.
# Run from the repo root (or anywhere — it resolves the repo from its own path).
#
# Usage: sudo bash deploy/02-deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

IMAGE=voice-service
CONTAINER=voice

# --- Preflight ------------------------------------------------------------------
if [[ ! -f .env ]]; then
  echo "ERROR: $REPO_DIR/.env not found." >&2
  echo "  cp .env.example .env   # then fill in the secrets (deploy/ENV-CHECKLIST.md)" >&2
  exit 1
fi

for var in SUPABASE_JWT_SECRET SUPABASE_SERVICE_ROLE_KEY; do
  if ! grep -qE "^${var}=.+" .env; then
    echo "ERROR: $var is empty in .env — required before deploy (see deploy/ENV-CHECKLIST.md)." >&2
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running (did you run deploy/01-provision.sh?)." >&2
  exit 1
fi

# --- Pull latest code (no-op on a fresh clone) -----------------------------------
if git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "==> Pulling latest code..."
  git -C "$REPO_DIR" pull --ff-only || echo "    (pull skipped — not fast-forwardable; deploying current checkout)"
fi

# --- Build ------------------------------------------------------------------------
echo "==> Building image '$IMAGE'..."
docker build -t "$IMAGE" .

# --- Run --------------------------------------------------------------------------
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "==> Removing existing '$CONTAINER' container..."
  docker rm -f "$CONTAINER"
fi

echo "==> Starting container (app bound to 127.0.0.1:8000 only)..."
# The hfcache volume persists Hugging Face model weights across restarts, so
# the model is only downloaded on the very first startup.
docker run -d --name "$CONTAINER" \
  --gpus all \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  -v hfcache:/root/.cache/huggingface \
  --restart unless-stopped \
  "$IMAGE"

echo "==> Waiting for the service to come up (first boot downloads model weights"
echo "    and can take several minutes)..."
for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "==> Service is up:"
    curl -fsS http://127.0.0.1:8000/healthz
    echo
    echo "==> Done. Next: bash deploy/smoke-test.sh https://voice.lifedailyos.app"
    exit 0
  fi
  sleep 5
done

echo "ERROR: service did not become healthy within 10 minutes. Logs:" >&2
docker logs --tail 100 "$CONTAINER" >&2
exit 1
