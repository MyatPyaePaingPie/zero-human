"""Wait for the latest Render deploy of reality-check to finish; print status + URL."""
import subprocess, time, httpx
k = subprocess.run(["security","find-generic-password","-s","RENDER_API_KEY","-w"],capture_output=True,text=True).stdout.strip()
c = httpx.Client(base_url="https://api.render.com/v1", headers={"Authorization": f"Bearer {k}"}, timeout=60)
svc = next(s["service"] for s in c.get("/services", params={"name": "reality-check", "limit": 20}).json() if s["service"]["name"] == "reality-check")
for _ in range(60):
    d = c.get(f"/services/{svc['id']}/deploys", params={"limit": 1}).json()[0]["deploy"]
    print(d["status"], d.get("commit", {}).get("id", "")[:7], flush=True)
    if d["status"] in ("live", "build_failed", "update_failed", "canceled"):
        break
    time.sleep(15)
print("url", svc["serviceDetails"]["url"])
