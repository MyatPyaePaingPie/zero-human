"""Print recent Render build/app logs for the reality-check service. Secret never printed."""
import subprocess, sys, httpx
k = subprocess.run(["security","find-generic-password","-s","RENDER_API_KEY","-w"],capture_output=True,text=True).stdout.strip()
c = httpx.Client(base_url="https://api.render.com/v1", headers={"Authorization": f"Bearer {k}"}, timeout=60)
svc = next(s["service"] for s in c.get("/services", params={"name": "reality-check", "limit": 20}).json() if s["service"]["name"] == "reality-check")
kind = sys.argv[1] if len(sys.argv) > 1 else "build"
r = c.get("/logs", params={"ownerId": svc["ownerId"], "resource": [svc["id"]], "limit": 100, "type": [kind]})
if r.status_code >= 300:
    print(r.status_code, r.text[:500]); sys.exit(1)
for l in r.json().get("logs", []):
    print(l.get("message", "")[:220])
