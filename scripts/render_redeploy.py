"""Trigger a deploy of the latest commit on the reality-check Render service."""
import subprocess, httpx
k = subprocess.run(["security","find-generic-password","-s","RENDER_API_KEY","-w"],capture_output=True,text=True).stdout.strip()
c = httpx.Client(base_url="https://api.render.com/v1", headers={"Authorization": f"Bearer {k}"}, timeout=60)
svc = next(s["service"] for s in c.get("/services", params={"name": "reality-check", "limit": 20}).json() if s["service"]["name"] == "reality-check")
r = c.post(f"/services/{svc['id']}/deploys", json={"clearCache": "do_not_clear"})
print(r.status_code, r.json().get("id"), r.json().get("commit", {}).get("id", "")[:7])
