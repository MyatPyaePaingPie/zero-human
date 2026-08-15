"""Create or update the Render web service for reality-check and set its env vars from the keychain.
Usage: .venv/bin/python scripts/render_deploy.py [--repo <github url>] [--branch main]
Never prints secret values. Prints the service URL and the deploy status."""
import argparse
import subprocess
import sys
import time

import httpx

API = "https://api.render.com/v1"
SERVICE = "reality-check"
SECRETS = ["GROQ_API_KEY", "OPENAI_API_KEY", "ZEROHUMAN_STRIPE_WRITE_KEY", "RC_PAYLINK_DEFAULT", "RC_PAYLINK_FULL_REALITY_CHECK",
           "TERAC_API_KEY", "REPLAY_API_KEY", "RC_ENVELOPE_SECRET", "LINQ_API_KEY", "LINQ_WEBHOOK_SECRET"]
PLAIN = {"PYTHON_VERSION": "3.12.6", "RC_DB": "/var/data/rc.db", "RC_ENVELOPE": "/var/data/envelope.json",
         "RC_DEADLINE_ISO": "2026-08-15T18:30:00-07:00", "RC_HUMAN_TIMEOUT_S": "1800", "TERAC_CPI_USD": "4.5",
         "TERAC_PROJECT_ID": "fskntvr1bh3szfuyj8jsem2r"}


def kc(name: str) -> str:
    return subprocess.run(["security", "find-generic-password", "-s", name, "-w"], capture_output=True, text=True).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="https://github.com/MyatPyaePaingPie/zero-human")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--plan", default="starter", choices=["free", "starter"])
    a = ap.parse_args()
    key = kc("RENDER_API_KEY")
    if not key.startswith("rnd_"):
        sys.exit("RENDER_API_KEY missing or wrong")
    c = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=60)

    owners = c.get("/owners", params={"limit": 20}).raise_for_status().json()
    owner_id = owners[0]["owner"]["id"]
    print("owner", owners[0]["owner"].get("name"), owner_id)

    if a.plan == "free":  # no disk on free: sqlite lives in the container; a redeploy wipes jobs (Stripe stays the revenue truth)
        PLAIN["RC_DB"] = "/tmp/rc.db"; PLAIN["RC_ENVELOPE"] = "/tmp/envelope.json"
    env_vars = [{"key": k, "value": v} for k, v in PLAIN.items()]
    for n in SECRETS:
        v = kc(n)
        if v:
            env_vars.append({"key": n, "value": v})
        else:
            print("skip (not in keychain):", n)

    svcs = c.get("/services", params={"name": SERVICE, "limit": 20}).raise_for_status().json()
    svc = next((s["service"] for s in svcs if s["service"]["name"] == SERVICE), None)
    if not svc:
        body = {
            "type": "web_service", "name": SERVICE, "ownerId": owner_id, "repo": a.repo, "branch": a.branch, "autoDeploy": "yes",
            "serviceDetails": {
                "runtime": "python", "plan": a.plan, "region": "oregon", "healthCheckPath": "/ledger",
                "envSpecificDetails": {"buildCommand": "pip install -e .", "startCommand": "uvicorn reality_check.api:app --host 0.0.0.0 --port $PORT"},
                **({"disk": {"name": "rc-data", "mountPath": "/var/data", "sizeGB": 1}} if a.plan != "free" else {}),
            },
            "envVars": env_vars,
        }
        r = c.post("/services", json=body)
        if r.status_code >= 300:
            sys.exit(f"create failed {r.status_code}: {r.text[:800]}")
        svc = r.json()["service"]
        print("created", svc["id"])
    else:
        print("exists", svc["id"])
        r = c.put(f"/services/{svc['id']}/env-vars", json=env_vars)
        if r.status_code >= 300:
            sys.exit(f"env update failed {r.status_code}: {r.text[:800]}")
        d = c.post(f"/services/{svc['id']}/deploys", json={"clearCache": "do_not_clear"})
        print("deploy triggered", d.status_code)
    url = svc.get("serviceDetails", {}).get("url") or f"https://{SERVICE}.onrender.com"
    # RC_PUBLIC_BASE must be the real URL
    c.put(f"/services/{svc['id']}/env-vars/RC_PUBLIC_BASE", json={"value": url})
    print("url", url)
    for _ in range(60):
        deps = c.get(f"/services/{svc['id']}/deploys", params={"limit": 1}).json()
        st = deps[0]["deploy"]["status"] if deps else "?"
        print("deploy:", st, flush=True)
        if st in ("live", "build_failed", "update_failed", "canceled", "deactivated"):
            break
        time.sleep(15)


if __name__ == "__main__":
    main()
