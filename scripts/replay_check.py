"""Read-only Replay QA check: auth + list projects. Creates nothing."""
import subprocess, httpx
k = subprocess.run(["security","find-generic-password","-s","REPLAY_API_KEY","-w"],capture_output=True,text=True).stdout.strip()
r = httpx.get("https://qa.replay.io/api/v1/projects", headers={"Authorization": f"Bearer {k}"}, timeout=20)
print(r.status_code, r.text[:500])
