"""Test env: throwaway DB, dev payment header, and a signed spend envelope (the gate is
fail-closed, so without one no paid arm would ever launch)."""
import json
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="rc-test-"))
os.environ["RC_DB"] = str(_tmp / "rc.db")
os.environ["RC_DEV"] = "1"
os.environ["RC_ENVELOPE"] = str(_tmp / "envelope.json")
os.environ["RC_ENVELOPE_SECRET"] = "test-secret"
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("ZEROHUMAN_STRIPE_RESTRICTED_KEY", None)
os.environ.pop("TERAC_API_KEY", None)

from reality_check.policy import envelope  # noqa: E402

_body = {"daily_cap_usd": 60, "per_job_cap_usd": 10, "min_margin_ratio": 0.2,
         "allowed_arms": ["ensemble", "linq_panel", "terac_general"],
         "expires_at": "2099-01-01T00:00:00+00:00", "signed_by": "test"}
_body["signature"] = envelope.sign(_body, "test-secret")
Path(os.environ["RC_ENVELOPE"]).write_text(json.dumps(_body))
