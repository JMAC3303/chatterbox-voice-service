#!/usr/bin/env bash
# Provision an Atlantic.net GPU server (Ubuntu 22.04) for the voice service.
#
# Idempotent: safe to re-run. Run it twice — the first run installs the NVIDIA
# driver and reboots; the second run (after reboot) installs Docker, the NVIDIA
# Container Toolkit, Caddy, and the firewall rules.
#
# Usage: sudo bash deploy/01-provision.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: run as root (sudo bash deploy/01-provision.sh)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# --- Phase 1: NVIDIA driver ---------------------------------------------------
if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then
  echo "==> Installing NVIDIA driver (ubuntu-drivers autoinstall)..."
  apt-get update
  apt-get install -y ubuntu-drivers-common
  ubuntu-drivers autoinstall
  echo
  echo "==> Driver installed. REBOOTING in 10s (Ctrl-C to cancel)."
  echo "    After reboot, SSH back in and re-run this script to continue."
  sleep 10
  reboot
fi

echo "==> NVIDIA driver OK:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

# --- Phase 2: Docker ----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker..."
  curl -fsSL https://get.docker.com | sh
else
  echo "==> Docker already installed."
fi

# --- Phase 3: NVIDIA Container Toolkit ----------------------------------------
if ! dpkg -s nvidia-container-toolkit >/dev/null 2>&1; then
  echo "==> Installing NVIDIA Container Toolkit..."
  distribution=$(. /etc/os-release; echo "$ID$VERSION_ID")
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list" \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update
  apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
else
  echo "==> NVIDIA Container Toolkit already installed."
fi

echo "==> Verifying GPU is visible inside Docker..."
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi \
  --query-gpu=name --format=csv,noheader

# --- Phase 4: Caddy (automatic HTTPS) ------------------------------------------
if ! command -v caddy >/dev/null 2>&1; then
  echo "==> Installing Caddy..."
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
else
  echo "==> Caddy already installed."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> Installing Caddyfile..."
install -m 644 "$SCRIPT_DIR/Caddyfile" /etc/caddy/Caddyfile
systemctl enable caddy
systemctl restart caddy

# --- Phase 5: Firewall ----------------------------------------------------------
echo "==> Configuring UFW (22, 80, 443 open; 8000 denied externally)..."
apt-get install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 8000/tcp
ufw --force enable
ufw status verbose

echo
echo "==> Provisioning complete."
echo "    Next: cp .env.example .env  (fill in secrets — see deploy/ENV-CHECKLIST.md)"
echo "    Then: sudo bash deploy/02-deploy.sh"
