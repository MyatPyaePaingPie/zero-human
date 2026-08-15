"""Text intake (issue #23): the whole product in one iMessage thread. A human texts the Linq
line with links (repo/slides/page, any subset) or a pitch; we ack immediately with no link
(Linq sandbox rule: first outbound carries no link), grade in the background, and text back the
result with the PDF + agent.md links once the hackathon rubric lands. RERUN re-fires the same
links as a before/after pair; HUMANS surfaces the async human-panel line when it settles.

Wired from ``linq_client.handle_inbound`` (see that module) after STOP handling and enrollment.
Everything here fails closed and is safe to call more than once for the same job: the send
functions gate on a state flag before texting.
"""
from __future__ import annotations

import os

import re
from typing import Any

from reality_check import sources, store
from reality_check.panels import PUBLIC_BASE

ASK_LINE = "Send me a link to your repo, your slides, or your landing page. Any one works, all three is best."
TEXT_PRICE_USD = 8.0
PAY_ACK_LINE = ("Got it. Reading your repo, deck, and page now. Feel free to text more before you pay: another link, "
                "your one-line pitch, your price. Next text is your payment link ($8); the report comes right after.")
ADDED_LINE = "Added your {what} to the same check."
PAY_LINE = "Reality Check, $8: {url}  You get the hackathon verdict, sponsor tracks, the autonomy grade, a PDF and an agent.md for your coding agent."
ACK_LINE = ("Got it. Reading your repo and page now. Grading it against today's rubric and the sponsor tracks. "
            "Give me about two minutes.")
RERUN_ACK_LINE = "Re-running on the same links..."
NOT_IN_YET_LINE = "Not in yet. I'll text you as soon as the panel settles."
CLOSING_LINE = "Reply RERUN after you fix things. Reply HUMANS to hear what 3 strangers said when it lands."

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+")

_HACKATHON_STAMP_LABELS = {
    "contender": "CONTENDER",
    "fixable_by_1830": "FIXABLE BY 18:30",
    "not_yet": "NOT YET",
    "not_run": "NOT RUN",
}


def parse_links(text: str) -> dict[str, Any]:
    """Split a text message into repo/deck/url links (via ``sources.detect``) plus whatever
    text is left over (the pitch). Any subset of link kinds may be present; only the first URL
    of each kind is kept."""
    text = text or ""
    out: dict[str, str | None] = {"repo": None, "deck": None, "url": None}
    remainder = text
    for m in _URL_RE.finditer(text):
        link = m.group(0)
        kind = sources.detect(link)
        if kind in ("repo", "deck", "page") and not out[{"page": "url"}.get(kind, kind)]:
            out[{"page": "url"}.get(kind, kind)] = link
        remainder = remainder.replace(link, " ")
    return {**out, "pitch": " ".join(remainder.split())}


def _has_link(links: dict) -> bool:
    return bool(links.get("repo") or links.get("deck") or links.get("url"))


def start_from_text(phone: str, text: str, *, before_job_id: str | None = None) -> dict:
    """Create the job for this text: full_reality_check, free (voi_routed floor, $0 budget --
    this product is free for the room today), buyer_id keyed off the rater identity so the same
    phone keeps one identity across jobs. Records the phone->job mapping. No links are ever put
    into a text sent from here -- only the job_id and the parsed links are returned to the
    caller, which decides what (if anything) to say."""
    from reality_check import judge, linq_client
    from reality_check.core.models import JudgeRequest

    links = parse_links(text)
    req = JudgeRequest(
        sku="full_reality_check",
        evidence_standard="human_backed",   # not a Reality Check without real people
        max_budget_usd=0.0 if text_is_free() else TEXT_PRICE_USD,
        buyer_id=f"text:{linq_client.rater_id(phone)}",
        notify_phone=phone,
        repo=links["repo"],
        deck=links["deck"],
        url=links["url"],
        input=links["pitch"] or "",
        before_job_id=before_job_id,
    )
    if text_is_free():
        v = judge.start(req)
        store.text_thread_put(linq_client.rater_id(phone), v.job_id, links)
        return {"job_id": v.job_id, "links": links, "paid": False, "pay_url": None}
    # paid path: the same pending_payment order the web flow uses; the Stripe poller/webhook calls
    # complete_session -> judge.start(paid_usd) when the Payment Link session is paid, which writes
    # the revenue row and (through the hackathon thread) triggers on_report_ready
    import uuid
    from reality_check import stripe_webhook
    job_id = uuid.uuid4().hex[:12]
    store.put_job(job_id, req.buyer_id, "pending_payment", req.model_dump(), {"text_thread": True})
    link = os.environ.get("RC_PAYLINK_TEXT") or stripe_webhook.pay_link("reality_check")
    pay_url = f"{link}?client_reference_id={job_id}" if link else None
    store.event(job_id, "order.created", {"sku": req.sku, "via": "text", "pay_url": pay_url})
    store.text_thread_put(linq_client.rater_id(phone), job_id, links)
    return {"job_id": job_id, "links": links, "paid": True, "pay_url": pay_url}


def text_is_free() -> bool:
    """RC_TEXT_FREE=1 skips the payment link (room override). Default OFF: the text thread sells."""
    return os.environ.get("RC_TEXT_FREE", "0") == "1"


def _open_job(phone_hash: str) -> dict | None:
    """The phone's newest job if it is still unpaid (pending_payment): everything the phone sends
    before paying attaches to it (Aria: same job until payment, no time window)."""
    last = store.text_thread_last(phone_hash)
    if not last:
        return None
    job = store.get_job(last["job_id"])
    if job and job["status"] == "pending_payment":
        return job
    return None


def attach_to_job(job: dict, text: str) -> dict:
    """Merge new links / pitch text into an open (unpaid) job's request. Returns what was added."""
    links = parse_links(text)
    req = dict(job["request"])
    added: list[str] = []
    for slot, what in (("repo", "repo"), ("deck", "deck"), ("url", "landing page")):
        if links.get(slot) and not req.get(slot):
            req[slot] = links[slot]
            added.append(what)
        elif links.get(slot) and req.get(slot) and req.get(slot) != links[slot]:
            req[slot] = links[slot]
            added.append(what)
    pitch = (links.get("pitch") or "").strip()
    if pitch and not pitch.upper() in ("PAY", "HUMANS", "RERUN"):
        req["input"] = ((req.get("input") or "").strip() + "\n" + pitch).strip()[:20000]
        if not added:
            added.append("note")
    store.update_request(job["job_id"], req)
    from reality_check import linq_client
    store.text_thread_put(linq_client.rater_id(job["request"].get("notify_phone") or ""), job["job_id"],
                          {k: req.get(k) for k in ("repo", "deck", "url")} | {"pitch": req.get("input")})
    store.event(job["job_id"], "text.attached", {"added": added})
    return {"job_id": job["job_id"], "added": added}


def handle_text(phone: str, text: str) -> dict:
    """Router for everything that isn't STOP (the caller handles STOP before this runs)."""
    from reality_check import linq_client

    t = (text or "").strip()
    first_word = t.split()[0].upper() if t.split() else ""
    phone_hash = linq_client.rater_id(phone)

    open_job = _open_job(phone_hash)
    if open_job and first_word not in ("RERUN", "HUMANS", "STOP"):
        if first_word == "PAY":
            link = os.environ.get("RC_PAYLINK_TEXT") or __import__("reality_check.stripe_webhook", fromlist=["pay_link"]).pay_link("reality_check")
            if link:
                linq_client.send(phone, PAY_LINE.format(url=f"{link}?client_reference_id={open_job['job_id']}"), job_id=open_job["job_id"])
            return {"action": "pay_resent", "job_id": open_job["job_id"]}
        res = attach_to_job(open_job, t)
        what = ", ".join(res["added"]) if res["added"] else "message"
        linq_client.send(phone, ADDED_LINE.format(what=what), job_id=open_job["job_id"])
        return {"action": "attached", "job_id": open_job["job_id"], "added": res["added"]}

    if first_word == "RERUN":
        last = store.text_thread_last(phone_hash)
        if not last:
            linq_client.send(phone, ASK_LINE)
            return {"action": "ask", "reason": "rerun_no_thread"}
        links = last["links"]
        reconstructed = " ".join(x for x in (links.get("repo"), links.get("deck"), links.get("url"), links.get("pitch")) if x)
        result = start_from_text(phone, reconstructed, before_job_id=last["job_id"])
        linq_client.send(phone, RERUN_ACK_LINE, job_id=result["job_id"])
        return {"action": "rerun", "job_id": result["job_id"], "before_job_id": last["job_id"]}

    if first_word == "HUMANS":
        last = store.text_thread_last(phone_hash)
        job_id = last["job_id"] if last else None
        answers = store.human_answers(job_id) if job_id else []
        if answers:
            on_humans_ready(job_id)
            return {"action": "humans", "job_id": job_id}
        linq_client.send(phone, NOT_IN_YET_LINE, job_id=job_id)
        return {"action": "humans_not_ready", "job_id": job_id}

    links = parse_links(t)
    if not _has_link(links):
        linq_client.send(phone, ASK_LINE)
        return {"action": "ask"}

    result = start_from_text(phone, t)
    if result.get("paid"):
        # first outbound never carries a link (Linq sandbox rule); the pay link is the second text
        linq_client.send(phone, PAY_ACK_LINE, job_id=result["job_id"])
        if result.get("pay_url"):
            linq_client.send(phone, PAY_LINE.format(url=result["pay_url"]), job_id=result["job_id"])
        else:
            store.event(result["job_id"], "text.no_paylink", {})
        return {"action": "pending_payment", "job_id": result["job_id"], "links": result["links"]}
    linq_client.send(phone, ACK_LINE, job_id=result["job_id"])
    return {"action": "started", "job_id": result["job_id"], "links": result["links"]}


# ---- outbound: report + humans lines, called once the background work lands -----------------

def _fmt_hackathon_stamp(stamp: str | None) -> str:
    stamp = stamp or "not_run"
    return _HACKATHON_STAMP_LABELS.get(stamp, stamp.replace("_", " ").upper())


def _fmt_business_stamp(stamp: str | None) -> str:
    return (stamp or "not_run").replace("_", " ").upper()


def _project_name(job: dict) -> str:
    src_list = ((job.get("state") or {}).get("sources") or {}).get("sources") or []
    for s in src_list:
        if s.get("kind") == "repo":
            title = (s.get("meta") or {}).get("title") or ""
            if title:
                return title.rsplit("/", 1)[-1]
    for s in src_list:
        if s.get("kind") == "page":
            title = (s.get("meta") or {}).get("title") or ""
            if title:
                return title[:60]
    repo = (job.get("request") or {}).get("repo")
    if repo:
        return repo.rstrip("/").rsplit("/", 1)[-1]
    return "Your project"


def _delta_line(before_job_id: str, rep_after: dict) -> str | None:
    from reality_check import report

    try:
        rep_before = report.build(before_job_id)
    except KeyError:
        return None
    before_status = {f["id"]: f.get("status") for f in rep_before["findings"]}
    after_status = {f["id"]: f.get("status") for f in rep_after["findings"]}
    fixed = sum(1 for fid, st in after_status.items()
                if fid in before_status and before_status[fid] != "pass" and st == "pass")
    regressed = sum(1 for fid, st in after_status.items()
                     if fid in before_status and before_status[fid] == "pass" and st != "pass")
    new_stamp = _fmt_hackathon_stamp(rep_after["stamps"].get("hackathon"))
    return f"fixed: {fixed}, regressed: {regressed}, new stamp {new_stamp}"


def _compose_result(job: dict, rep: dict) -> str:
    project = _project_name(job)
    job_id = job["job_id"]
    stamps = rep.get("stamps") or {}
    autonomy = rep.get("autonomy")
    autonomy_str = f"Autonomous {autonomy['k_hold']}/{autonomy['n']}" if autonomy else "Autonomous not run"
    line1 = (f"{project}: Hackathon {_fmt_hackathon_stamp(stamps.get('hackathon'))} · {autonomy_str} · "
             f"Business {_fmt_business_stamp(stamps.get('business'))}")

    top3 = rep.get("top3") or []
    fixes = " ".join(f"{i + 1}) {str(t)[:90]}" for i, t in enumerate(top3[:3]))
    line2 = f"Do first: {fixes}" if fixes else ""

    sponsors = ((rep.get("hackathon") or {}).get("sponsors")) or {}
    qualifies = [e.get("name", "") for e in sponsors.get("qualifies", [])]
    cheapest = [e.get("name", "") for e in sponsors.get("cheapest_to_add", [])]
    sponsor_line = f"Sponsor tracks you qualify for: {', '.join(qualifies) if qualifies else 'none yet'}."
    if cheapest:
        sponsor_line += f" Cheapest to add: {cheapest[0]}."

    pdf_url = f"{PUBLIC_BASE}/report/{job_id}.pdf"
    agent_url = f"{PUBLIC_BASE}/report/{job_id}/agent.md"
    line4 = f"Full report (PDF): {pdf_url}   For your coding agent: {agent_url}"

    before_job_id = (job.get("request") or {}).get("before_job_id")
    lines = [line1, line2, sponsor_line, line4, CLOSING_LINE]
    if before_job_id:
        delta = _delta_line(before_job_id, rep)
        if delta:
            lines.insert(0, delta)
    return "\n".join(p for p in lines if p)


GRADED_LINE = ("Graded. {n} strangers are reading it now; your report arrives when they finish (usually under "
               "30 minutes). It is not a report without them.")
WAITING_LINE = ("Still waiting on the humans. Your grade is done, but a Reality Check without real people is not "
                "one, so I am holding the report until they answer. I will text the moment they do.")


def _final_ready(job: dict) -> bool:
    """The report a person receives must contain the humans' answers (Aria, 15:35): final send only
    when the rubric has landed AND at least one human has answered; before that, status texts only."""
    st = job.get("state") or {}
    return st.get("hackathon") is not None and bool(store.human_answers(job["job_id"]))


def _send_final(job: dict) -> bool:
    from reality_check import linq_client, report
    job_id = job["job_id"]
    st = job.get("state") or {}
    if st.get("text_result_sent"):
        return False
    phone = (job.get("request") or {}).get("notify_phone")
    rep = report.build(job_id)
    text = _compose_result(job, rep) + "\n" + _compose_humans(job_id)
    linq_client.send(phone, text, job_id=job_id)
    store.patch_job_state(job_id, "text_result_sent", True)
    store.event(job_id, "text.result_sent", {})
    return True


def on_report_ready(job_id: str) -> None:
    """Rubric landed (judge.py hackathon thread). If the humans are already in, send the final
    report; otherwise one status text ("graded, humans reading") and wait. Idempotent."""
    from reality_check import linq_client

    job = store.get_job(job_id)
    if not job or not (job.get("request") or {}).get("notify_phone"):
        return
    st = job.get("state") or {}
    if st.get("hackathon") is None:
        return
    if _final_ready(job):
        _send_final(job)
        return
    if not st.get("text_graded_sent"):
        n = (st.get("panel") or {}).get("n") or 3
        linq_client.send(job["request"]["notify_phone"], GRADED_LINE.format(n=n), job_id=job_id)
        store.patch_job_state(job_id, "text_graded_sent", True)
        store.event(job_id, "text.graded_sent", {})


def on_humans_timeout(job_id: str) -> None:
    """The panel timed out with no answers: never send a model-only report; one status text and
    keep the rate page open (settle_on_timeout still records the model verdict for the ledger)."""
    from reality_check import linq_client

    job = store.get_job(job_id)
    if not job or not (job.get("request") or {}).get("notify_phone"):
        return
    st = job.get("state") or {}
    if st.get("text_result_sent") or st.get("text_wait_sent"):
        return
    if store.human_answers(job_id):
        on_humans_ready(job_id)
        return
    linq_client.send(job["request"]["notify_phone"], WAITING_LINE, job_id=job_id)
    store.patch_job_state(job_id, "text_wait_sent", True)
    store.event(job_id, "text.wait_sent", {})


def _compose_humans(job_id: str) -> str:
    answers = store.human_answers(job_id)
    if not answers:
        return ""
    n = len(answers)
    claim0 = [a for a in answers if a.get("claim_idx") == 0]
    pool = claim0 or answers
    yes0 = sum(1 for a in pool if a.get("answer_yes"))
    quotes = [a["free_text"].strip()[:80] for a in answers if (a.get("free_text") or "").strip()][:2]
    text = f"{n} strangers read your pitch: {yes0} of {len(pool)} could say what it does."
    if quotes:
        text += " " + " ".join(f'"{q}"' for q in quotes)
    return text + " Details in the PDF."


def on_humans_ready(job_id: str) -> None:
    """Human answers landed (settle or later): send the final report if the rubric is in too;
    else wait for on_report_ready to do it. Idempotent."""
    job = store.get_job(job_id)
    if not job or not (job.get("request") or {}).get("notify_phone"):
        return
    if _final_ready(job):
        _send_final(job)


def merge_open_jobs(rater: str) -> dict:
    """Operator: collapse a phone's several pending_payment jobs into the newest one (links merged),
    cancel the rest, text one line with the surviving pay link."""
    from reality_check import linq_client, stripe_webhook
    with store.conn() as c:
        rows = c.execute("SELECT job_id, request, status FROM jobs WHERE buyer_id=? AND status='pending_payment' ORDER BY created_at DESC",
                         (f"text:{rater}",)).fetchall()
    jobs = [{"job_id": r["job_id"], "request": __import__("json").loads(r["request"])} for r in rows]
    if not jobs:
        return {"merged": None, "cancelled": []}
    keep = jobs[0]
    req = dict(keep["request"])
    for other in jobs[1:]:
        for slot in ("repo", "deck", "url"):
            if not req.get(slot) and other["request"].get(slot):
                req[slot] = other["request"][slot]
        extra = (other["request"].get("input") or "").strip()
        if extra and extra not in (req.get("input") or ""):
            req["input"] = ((req.get("input") or "") + "\n" + extra).strip()[:20000]
        with store.conn() as c:
            c.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE job_id=?", (store.now(), other["job_id"]))
        store.event(other["job_id"], "order.cancelled", {"merged_into": keep["job_id"]})
    store.update_request(keep["job_id"], req)
    store.text_thread_put(rater, keep["job_id"], {k: req.get(k) for k in ("repo", "deck", "url")} | {"pitch": req.get("input")})
    phone = req.get("notify_phone")
    link = os.environ.get("RC_PAYLINK_TEXT") or stripe_webhook.pay_link("reality_check")
    if phone and link:
        linq_client.send(phone, f"One check, all your links (repo, deck, page). Use this single link to pay: {link}?client_reference_id={keep['job_id']}", job_id=keep["job_id"])
    return {"merged": keep["job_id"], "cancelled": [j["job_id"] for j in jobs[1:]], "request": {k: req.get(k) for k in ("repo", "deck", "url")}}
