"""The v2 human brief page (docs/specs/human-brief.md sections 2-5).

`full_reality_check` jobs send Terac respondents here instead of the v1 claim checklist: one
phone-sized screen of stimulus (their landing page first screen, their first slide, or the README
when a repo is all we have), the team's pitch, the price line, then the six questions a stranger
answers better than a model can.

On submit we store the whole brief (store.human_briefs) AND write claim-level answers into
human_answers, so judge.on_human_answer settles the job unchanged: q1 -> clarity/what-it-does,
q2 -> demand/payer, q3 -> demand/reachable-audience. No panel handle is needed anywhere.
"""
from __future__ import annotations

import html
import re

from fastapi.responses import HTMLResponse, RedirectResponse

from reality_check import store

PANEL_VERSION = "v2"

_DONT_KNOW = ("don't know", "dont know", "no idea", "not sure", "unsure", "no clue", "?", "idk", "n/a", "na", "nothing")
_NO_ONE = ("no one", "noone", "nobody", "none", "no-one")
_PRICE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?(?:\s?(?:/|per\s)\s?[a-z]+)?", re.I)

_LABELS = {"page": "their landing page", "deck": "their first slide", "repo": "from their README"}
_LINK_LABELS = {"page": "Open the full landing page", "deck": "Open the deck", "repo": "Open the repo"}


def applies(job: dict) -> bool:
    return (job.get("request") or {}).get("sku") == "full_reality_check"


# --- stimulus -----------------------------------------------------------------------------------

def _sources(job: dict) -> list[dict]:
    return ((job["state"].get("sources") or {}).get("sources")) or []


def ensure_page_source(job_id: str, job: dict) -> None:
    """A job created as pitch + url has no resolved sources (judge._resolve_sources only reads when
    a repo/deck was given, or a url with no pitch). The panel still has to show the landing page, so
    read it once here and cache it on state.sources. Fails soft: the link-only block still renders."""
    url = (job["request"] or {}).get("url") or ""
    if not url.startswith("http") or any(s.get("kind") == "page" and (s.get("first_screen") or "").strip() for s in _sources(job)):
        return
    try:
        from reality_check import judge, sources as sources_mod
        src = sources_mod.read_page(url)
        if not (src.text or "").strip():
            store.event(job_id, "rate.page_read_empty", {"url": url, "meta": src.meta})
            return
        d = src.as_dict()
        row = {k: v for k, v in d.items() if k != "text"} | {
            "chars": len(d.get("text") or ""), "first_screen": judge._first_screen(d), "link": url}
    except Exception as exc:  # pragma: no cover - network failure must never break the panel page
        store.event(job_id, "rate.page_read_failed", {"error": str(exc)[:200]})
        return
    st = job["state"].get("sources") or {"source_kinds": [], "sources": [], "warnings": []}
    # replace an older page row that predates first_screen (jobs created before rate v2)
    st["sources"] = [row] + [x for x in (st.get("sources") or []) if x.get("kind") != "page"]
    st["source_kinds"] = ["page"] + [k for k in st.get("source_kinds", []) if k != "page"]
    job["state"]["sources"] = st
    store.patch_job_state(job_id, "sources", st)


def ensure_repo_source(job_id: str, job: dict) -> None:
    """Older jobs stored the repo source without first_screen; read the README once (2 API calls)."""
    repo = (job["request"] or {}).get("repo") or ""
    if not repo.startswith("http") or any(s.get("kind") == "repo" and (s.get("first_screen") or "").strip() for s in _sources(job)):
        return
    try:
        from reality_check import judge, sources as sources_mod
        src = sources_mod.read_repo(repo)
        if not (src.text or "").strip():
            return
        d = src.as_dict()
        row = {k: v for k, v in d.items() if k != "text"} | {
            "chars": len(d.get("text") or ""), "first_screen": judge._first_screen(d), "link": repo}
    except Exception as exc:  # pragma: no cover
        store.event(job_id, "rate.repo_read_failed", {"error": str(exc)[:200]})
        return
    st = job["state"].get("sources") or {"source_kinds": [], "sources": [], "warnings": []}
    st["sources"] = [x for x in (st.get("sources") or []) if x.get("kind") != "repo"] + [row]
    if "repo" not in st.get("source_kinds", []):
        st["source_kinds"] = list(st.get("source_kinds", [])) + ["repo"]
    job["state"]["sources"] = st
    store.patch_job_state(job_id, "sources", st)


def stimulus(job: dict) -> list[dict]:
    """[{label, text, link, link_label}] in brief order: page, then deck, then README only when
    neither exists (a repo alone means the README is the primary source)."""
    by_kind = {s.get("kind"): s for s in _sources(job) if (s.get("first_screen") or "").strip()}
    out = []
    for kind in ("page", "deck"):
        s = by_kind.get(kind)
        if s:
            out.append({"kind": kind, "label": _LABELS[kind], "text": s["first_screen"],
                        "link": s.get("link") or s.get("ref") or "", "link_label": _LINK_LABELS[kind]})
    url = (job.get("request") or {}).get("url") or ""
    if not any(o["kind"] == "page" for o in out) and url.startswith("http"):
        # page text could not be read (blocked, empty, slow): still show the screenshot + link
        out.insert(0, {"kind": "page", "label": _LABELS["page"], "text": "", "link": url, "link_label": _LINK_LABELS["page"]})
    if by_kind.get("repo"):
        # the README first paragraph rides along whenever a repo was given (last, so page/deck lead)
        s = by_kind["repo"]
        out.append({"kind": "repo", "label": _LABELS["repo"], "text": s["first_screen"],
                    "link": s.get("link") or s.get("ref") or "", "link_label": _LINK_LABELS["repo"]})
    return out


def pitch_line(job: dict) -> str:
    pitch = next((s for s in _sources(job) if s.get("kind") == "pitch"), None)
    text = (pitch or {}).get("first_screen") or ""
    if not text:
        raw = (job["request"].get("input") or "").strip()
        text = "" if raw.startswith("===") else raw
    line = " ".join(text.split())
    return line[:300]


def price_line(job: dict) -> str:
    hay = " ".join([pitch_line(job)] + [b["text"] for b in stimulus(job)])
    m = _PRICE_RE.search(hay)
    return f"Their price: {m.group(0).strip()}" if m else "No price is shown."


_GSLIDES_RE = re.compile(r"docs\.google\.com/presentation/d/(?:e/)?([A-Za-z0-9_-]{8,})")
_THUMB = "https://image.thum.io/get/width/900/crop/1200/noanimate/"


def _media(kind: str, link: str) -> str:
    """A picture beats a paragraph for a stranger with thirty seconds: a live screenshot for the
    landing page, the real slide for a Google deck. Both degrade to the text block below."""
    if not link.startswith("http"):
        return ""
    if kind == "page":
        return (f'<img class=shot loading=lazy src="{html.escape(_THUMB + link)}" alt="their landing page, first screen" '
                f'onerror="this.style.display=\'none\'">')
    if kind == "deck":
        m = _GSLIDES_RE.search(link)
        if m:
            embed = f"https://docs.google.com/presentation/d/{m.group(1)}/embed?start=false&loop=false"
            return f'<div class=embed><iframe src="{html.escape(embed)}" allowfullscreen title="their first slide"></iframe></div>'
    return ""


# --- render -------------------------------------------------------------------------------------

_CSS = """body{font:17px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
max-width:34rem;margin:0 auto;padding:1.2rem 1rem 4rem;color:#111;background:#fff}
h1{font-size:1.25rem;margin:0 0 .4rem}p.lede{color:#444;margin:0 0 1.2rem}
section.stim{border:1px solid #ddd;border-radius:10px;padding:.7rem .9rem;margin:.7rem 0;background:#fafafa}
section.stim h2{font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:#666;margin:0 0 .4rem}
section.stim pre{white-space:pre-wrap;word-break:break-word;font:inherit;margin:0}
section.stim a{font-size:.9rem}
section.stim img.shot{display:block;width:100%;max-height:40vh;object-fit:cover;object-position:top;border:1px solid #ddd;border-radius:8px;margin-bottom:.5rem;background:#fff}
section.stim .embed{position:relative;width:100%;padding-top:56.25%;margin-bottom:.5rem}
section.stim .embed iframe{position:absolute;inset:0;width:100%;height:100%;border:1px solid #ddd;border-radius:8px}
fieldset{border:0;padding:0;margin:1.4rem 0 0}legend{font-weight:600;padding:0;margin-bottom:.4rem}
label.opt{display:inline-block;margin:.2rem 1rem .2rem 0}
input[type=text],textarea{width:100%;font:inherit;padding:.55rem;border:1px solid #bbb;border-radius:8px;box-sizing:border-box}
textarea{min-height:3.4rem}
button{font:inherit;width:100%;padding:.9rem;margin-top:1.6rem;border-radius:10px;border:1px solid #111;background:#111;color:#fff}
.sub{font-size:.9rem;color:#555;margin:.3rem 0 0}"""


def _radio(name: str, value: str, label: str, required: bool = False) -> str:
    req = " required" if required else ""
    return f'<label class=opt><input type=radio name="{name}" value="{value}"{req}> {html.escape(label)}</label>'


def render(job_id: str, job: dict, *, src: str, respondent: str, terac_id: str | None) -> str:
    ensure_page_source(job_id, job)
    ensure_repo_source(job_id, job)
    if job["state"].get("panel_version") != PANEL_VERSION:
        store.patch_job_state(job_id, "panel_version", PANEL_VERSION)
    blocks = []
    stim = stimulus(job)
    url = (job["request"] or {}).get("url") or ""
    if not stim and url.startswith("http"):
        # we could not read the page (blocked, slow, JS-only): give them the real thing to look at
        blocks.append(f'<section class=stim><h2>{_LABELS["page"]}</h2>{_media("page", url)}'
                      f'<p><a href="{html.escape(url)}" rel="noopener nofollow" target="_blank">{html.escape(url)}</a></p></section>')
    for b in stim:
        link = (f'<p><a href="{html.escape(b["link"])}" rel="noopener nofollow" target="_blank">{html.escape(b["link_label"])}</a></p>'
                if b["link"].startswith("http") else "")
        blocks.append(f'<section class=stim><h2>{html.escape(b["label"])}</h2>'
                      f'{_media(b["kind"], b["link"])}<pre>{html.escape(b["text"])}</pre>{link}</section>')
    pitch = pitch_line(job)
    if pitch:
        blocks.append(f'<section class=stim><h2>their pitch, in their words</h2><pre>{html.escape(pitch)}</pre></section>')
    blocks.append(f'<p class=sub>{html.escape(price_line(job))}</p>')
    hidden = (f'<input type=hidden name="src" value="{html.escape(src)}">'
              f'<input type=hidden name="respondent" value="{html.escape(respondent)}">'
              f'<input type=hidden name="panel_version" value="v2">')
    if terac_id:
        hidden += f'<input type=hidden name="teracSubmissionId" value="{html.escape(terac_id)}">'
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Read this and answer honestly</title><style>{_CSS}</style>
<h1>Read this like you just stumbled on it.</h1>
<p class=lede>Then answer honestly. We are testing the company, not you. About three minutes. No right answers, no web searching.</p>
{''.join(blocks)}
<form method=post action="/rate/{job_id}">{hidden}
<fieldset><legend>1. In one line: what does this company do, and who is it for?</legend>
<textarea name=q1_what required></textarea></fieldset>
<fieldset><legend>2. Would you pay for this?</legend>
{_radio('q2_pay', 'yes', 'Yes', True)}{_radio('q2_pay', 'no', 'No')}
<p class=sub>Why, or why not?</p><textarea name=q2_why></textarea>
<p class=sub>If yes: what would you expect it to cost?</p><input type=text name=q2_price_guess></fieldset>
<fieldset><legend>3. Who do you know who has this problem?</legend>
<p class=sub>A role or type of person, or "no one".</p><input type=text name=q3_who required></fieldset>
<fieldset><legend>4. What is the one thing that would stop you from buying today?</legend>
<textarea name=q4_stopper required></textarea></fieldset>
<fieldset><legend>5. This company is run mostly by AI, with few or no people involved. Knowing that, are you more, less, or equally willing to buy?</legend>
{_radio('q5_ai_effect', 'more', 'More', True)}{_radio('q5_ai_effect', 'less', 'Less')}{_radio('q5_ai_effect', 'same', 'Equally willing')}
<p class=sub>Why?</p><textarea name=q5_why></textarea></fieldset>
<fieldset><legend>6. Does this look like a real business or a weekend project? (optional)</legend>
{_radio('q6_real', 'real', 'A real business')}{_radio('q6_real', 'weekend', 'A weekend project')}
<p class=sub>Why?</p><textarea name=q6_why></textarea></fieldset>
<button type=submit>Send my answers</button></form>"""


# --- submit -------------------------------------------------------------------------------------

def _said_something(text: str) -> bool:
    t = " ".join(text.split()).strip().lower().rstrip(".!")
    return bool(t) and t not in _DONT_KNOW and not any(t.startswith(d) for d in _DONT_KNOW)


def _claim_idx(job: dict, claim_id: str) -> int | None:
    for c in job["state"].get("claims", []):
        if c.get("claim_id") == claim_id:
            return c["idx"]
    return None


def _thanks(msg: str) -> HTMLResponse:
    return HTMLResponse("<meta name=viewport content='width=device-width,initial-scale=1'>"
                        f"<p style='font:17px/1.5 -apple-system,system-ui,sans-serif;margin:3rem 1rem'>{html.escape(msg)}</p>")


def submit(job_id: str, job: dict, form, *, src: str, respondent: str):
    terac_id = str(form.get("teracSubmissionId") or "") or None
    answers = {
        "job": job_id, "submission_id": terac_id, "respondent": respondent,
        "q1_what": str(form.get("q1_what", "")).strip()[:2000], "q1_match": None,
        "q2_pay": str(form.get("q2_pay", "")).strip().lower() == "yes",
        "q2_why": str(form.get("q2_why", "")).strip()[:2000],
        "q2_price_guess": str(form.get("q2_price_guess", "")).strip()[:120],
        "q3_who": str(form.get("q3_who", "")).strip()[:500],
        "q4_stopper": str(form.get("q4_stopper", "")).strip()[:2000],
        "q5_ai_effect": str(form.get("q5_ai_effect", "")).strip().lower() or None,
        "q5_why": str(form.get("q5_why", "")).strip()[:2000],
        "q6_real": str(form.get("q6_real", "")).strip().lower() or None,
        "q6_why": str(form.get("q6_why", "")).strip()[:2000],
        "panel_version": PANEL_VERSION,
    }
    if job["state"].get("panel_version") != PANEL_VERSION:
        store.patch_job_state(job_id, "panel_version", PANEL_VERSION)
    if not store.add_human_brief(job_id, respondent, src, terac_id, answers):
        store.event(job_id, "human.duplicate", {"src": src, "respondent": respondent[:16], "panel_version": PANEL_VERSION})
        return _redirect_or_thanks(terac_id, src, respondent, "Already counted. Thank you.")

    # map into the settle path: judge.on_human_answer counts claim_idx 0 answers, unchanged
    understood = _said_something(answers["q1_what"])
    free0 = answers["q1_what"] + (f" | would not buy because: {answers['q4_stopper']}" if answers["q4_stopper"] else "")
    store.add_human_answer(job_id, src, respondent, understood, free0, claim_idx=0)
    payer_idx = _claim_idx(job, "demand/payer")
    if payer_idx is not None:
        why = answers["q2_why"] + (f" (expects {answers['q2_price_guess']})" if answers["q2_price_guess"] else "")
        store.add_human_answer(job_id, src, respondent, answers["q2_pay"], why, claim_idx=payer_idx)
    reach_idx = _claim_idx(job, "demand/reachable-audience")
    if reach_idx is not None:
        who = answers["q3_who"]
        knows = _said_something(who) and " ".join(who.split()).lower().rstrip(".!") not in _NO_ONE
        store.add_human_answer(job_id, src, respondent, knows, who, claim_idx=reach_idx)

    store.event(job_id, "human.answered", {"src": src, "panel_version": PANEL_VERSION, "pay": answers["q2_pay"],
                                           "ai_effect": answers["q5_ai_effect"]})
    from reality_check import judge, textflow
    judge.on_human_answer(job_id)
    try:
        textflow.on_humans_ready(job_id)
    except Exception as exc:  # pragma: no cover - notification must never eat a respondent's answer
        store.event(job_id, "text.error", {"error": str(exc)[:200]})
    return _redirect_or_thanks(terac_id, src, respondent, "Thank you. That is everything we needed.")


def _redirect_or_thanks(terac_id: str | None, src: str, respondent: str, msg: str):
    from reality_check.api import TERAC_CALLBACK
    ident = terac_id or (respondent if src == "terac" else None)
    if ident:
        return RedirectResponse(f"{TERAC_CALLBACK}?teracSubmissionId={ident}&result=completed", status_code=303)
    return _thanks(msg)
