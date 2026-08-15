#!/usr/bin/env bash
# Keep the free-tier Render service warm (it sleeps after ~15 min idle, taking the Stripe poller with it).
URL="${1:-https://reality-check-0f80.onrender.com}"
while true; do curl -s -o /dev/null -w "$(date +%H:%M:%S) %{http_code}\n" "$URL/ledger"; sleep 240; done
