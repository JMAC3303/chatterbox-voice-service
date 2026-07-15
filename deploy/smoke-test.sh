#!/usr/bin/env bash
# First smoke test on the Atlantic box (per MONDAY-HANDOFF):
#   1. GET /healthz            -> {"status":"ok", "variant": ...}
#   2. Authenticated POST /tts -> audio/mpeg bytes
#   3. Reminder to confirm a voice_usage row landed in the shared DB.
#
# Usage:
#   bash deploy/smoke-test.sh https://voice.lifedailyos.app
#   SUPABASE_ACCESS_TOKEN=<jwt> bash deploy/smoke-test.sh https://voice.lifedailyos.app
#
# The access token is a signed-in user's Supabase JWT (grab one from an app
# session's Authorization header, or mint one via supabase.auth.signInWithPassword).
set -euo pipefail

HOST="${1:-http://127.0.0.1:8000}"
TOKEN="${SUPABASE_ACCESS_TOKEN:-}"

echo "==> 1/3 GET $HOST/healthz"
health=$(curl -fsS "$HOST/healthz")
echo "    $health"
echo "$health" | grep -q '"status":"ok"' \
  || { echo "FAIL: /healthz did not return status ok" >&2; exit 1; }

if [[ -z "$TOKEN" ]]; then
  echo
  echo "==> 2/3 SKIPPED: set SUPABASE_ACCESS_TOKEN=<user jwt> to run the /tts test."
  echo "==> Health check PASSED."
  exit 0
fi

echo
echo "==> 2/3 GET $HOST/voices (authenticated)"
curl -fsS "$HOST/voices" -H "Authorization: Bearer $TOKEN" -H "X-Client-App: smoke-test"
echo

echo
echo "==> 3/3 POST $HOST/tts (short text, default voice)"
out="$(mktemp /tmp/voice-smoke-XXXX).mp3"
http_code=$(curl -sS -o "$out" -w '%{http_code}' "$HOST/tts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Client-App: smoke-test" \
  -H "Content-Type: application/json" \
  -d '{"text":"Be still and know that I am God.","voice_id":"builtin/default.wav"}')

if [[ "$http_code" != "200" ]]; then
  echo "FAIL: /tts returned HTTP $http_code:" >&2
  cat "$out" >&2
  exit 1
fi

size=$(wc -c < "$out")
echo "    OK — wrote $size bytes of audio to $out"
[[ "$size" -gt 1000 ]] || { echo "FAIL: audio suspiciously small" >&2; exit 1; }

echo
echo "==> Smoke test PASSED."
echo "    Final check: confirm a row landed in public.voice_usage"
echo "    (operation='tts', app='smoke-test') in the shared Supabase project."
