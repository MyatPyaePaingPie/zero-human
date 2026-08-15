---
name: wave-deploy
description: Deploy Reality Check to Render at the end of a wave (free tier wipes the DB), then re-run the sweep and verify live. Use only at wave boundaries in _meta/plans/2026-08-15-issue-queue-dag.md.
---
# wave-deploy
1. `.venv/bin/pytest -q` green; `git log --oneline origin/main..HEAD` empty after push.
2. Deploy per `scripts/` (Render API key in keychain as RENDER_API_KEY). Wait for the health check on
   https://reality-check-0f80.onrender.com/.
3. Re-run the sweep (`POST /sweep`), check `/sweep` renders, spot-check one `/verdict/{job}`.
4. Receipt on #18: deployed sha, what changed live, DB state (wiped, expected).
Committed, pushed, deployed, working are four states; say which you verified.
