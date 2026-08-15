"""Linq: verify the key, list our lines, and create the inbound webhook subscription pointing at
the public URL. Stores the returned signing secret in keychain LINQ_WEBHOOK_SECRET (never printed)."""
import subprocess, sys, httpx
BASE = "https://api.linqapp.com/api/partner/v3"
def kc(n): return subprocess.run(["security","find-generic-password","-s",n,"-w"],capture_output=True,text=True).stdout.strip()
key = kc("LINQ_API_KEY")
h = {"Authorization": f"Bearer {key}"}
r = httpx.get(f"{BASE}/phone_numbers", headers=h, timeout=20)
print("phone_numbers", r.status_code, r.text[:400])
if r.status_code != 200 or len(sys.argv) < 2:
    sys.exit(0)
target = sys.argv[1]
subs = httpx.get(f"{BASE}/webhook-subscriptions", headers=h, timeout=20)
j = subs.json() if subs.status_code == 200 else {}
lst = j.get("webhook_subscriptions") or j.get("data") or (j if isinstance(j, list) else [])
existing = [s for s in lst if str(s.get("target_url", "")).startswith(target)]
if existing:
    print("subscription exists", existing[0].get("id")); sys.exit(0)
c = httpx.post(f"{BASE}/webhook-subscriptions", headers=h, json={"target_url": f"{target}/linq/webhook?version=2026-02-03", "subscribed_events": ["message.received"]}, timeout=20)
print("create", c.status_code, {k: v for k, v in c.json().items() if k != "signing_secret"} if c.status_code < 300 else c.text[:300])
if c.status_code < 300 and c.json().get("signing_secret"):
    subprocess.run(["security","add-generic-password","-s","LINQ_WEBHOOK_SECRET","-a",subprocess.run(["id","-un"],capture_output=True,text=True).stdout.strip(),"-w",c.json()["signing_secret"],"-U"],check=True)
    print("LINQ_WEBHOOK_SECRET stored")
