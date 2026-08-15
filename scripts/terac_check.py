"""Read-only Terac check: auth, projects, opportunities. Launches nothing, spends nothing."""
import subprocess, sys, httpx
k = subprocess.run(["security","find-generic-password","-s","TERAC_API_KEY","-w"],capture_output=True,text=True).stdout.strip()
h = {"Authorization": f"Bearer {k}"}
for path in ("/projects", "/opportunities", "/feasibility/requests"):
    r = httpx.get(f"https://terac.com/api/external/v2{path}", headers=h, timeout=20)
    print(path, r.status_code, r.text[:400].replace("\n"," "))
