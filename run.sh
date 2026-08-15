#!/usr/bin/env bash
# Local runner: secrets from the macOS keychain (service name == env var name), never from files.
set -euo pipefail
cd "$(dirname "$0")"
for name in REPLAY_API_KEY RC_PAYLINK_DEFAULT ZEROHUMAN_STRIPE_WRITE_KEY ZEROHUMAN_STRIPE_RESTRICTED_KEY ZEROHUMAN_STRIPE_PUBLISHABLE_KEY TERAC_API_KEY GROQ_API_KEY OPENAI_API_KEY RC_ENVELOPE_SECRET; do
  if [ -z "${!name:-}" ]; then
    if v="$(security find-generic-password -s "$name" -w 2>/dev/null)"; then export "$name=$v"; else echo "run.sh: $name not in keychain (continuing)" >&2; fi
  fi
done
export RC_PUBLIC_BASE="${RC_PUBLIC_BASE:-http://localhost:8000}"
export RC_HUMAN_TIMEOUT_S="${RC_HUMAN_TIMEOUT_S:-1800}"
export RC_DEADLINE_ISO="${RC_DEADLINE_ISO:-2026-08-15T18:30:00-07:00}"
export RC_DB="${RC_DB:-demo.db}"
if [ -n "${RC_ENVELOPE_SECRET:-}" ] && [ ! -f state/envelope.json ]; then
  cp state/envelope.example.json state/envelope.json && .venv/bin/python -m reality_check.policy.envelope sign
fi
exec .venv/bin/uvicorn reality_check.api:app --host 0.0.0.0 --port "${PORT:-8000}"
