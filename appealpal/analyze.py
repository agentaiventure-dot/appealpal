"""Read a denial letter, extract the facts that matter for an appeal, validate them, and never invent a date or a quote."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from .llm import ChatClient

SYSTEM = (
    "You help people understand a letter that denies a health-insurance claim, prior authorisation, or a benefit. "
    "Extract only what the letter states. Quote the letter verbatim for the denial reason and for any deadline sentence. "
    "Never invent dates, policy numbers or contact details; use an empty string when the letter does not state something. "
    "Explain the denial reason in plain language at a reading level a 12-year-old can follow. "
    "Answer with a JSON object with exactly these keys: "
    "denial_type (one of: claim, prior_authorization, benefit, other), "
    "reason_quote (string, verbatim), reason_plain (string), "
    "deadline_quote (string, verbatim sentence about the appeal deadline, or empty), deadline_days (integer, or 0 if not stated), "
    "deadline_date (YYYY-MM-DD if the letter states an explicit date, else empty), letter_date (YYYY-MM-DD if stated, else empty), "
    "appeal_channel (string: how the letter says to appeal, verbatim or empty), reference_ids (array of strings quoted from the letter), "
    "evidence_needed (array of short strings: documents that would rebut the stated reason), "
    "questions_to_ask (array of short strings: questions for the insurer or doctor), "
    "external_review_available (boolean: true only if the letter mentions an independent or external review)."
)
KEYS = {"denial_type": str, "reason_quote": str, "reason_plain": str, "deadline_quote": str, "deadline_days": int, "deadline_date": str,
        "letter_date": str, "appeal_channel": str, "reference_ids": list, "evidence_needed": list, "questions_to_ask": list,
        "external_review_available": bool}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(r: Any) -> List[str]:
    problems: List[str] = []
    if not isinstance(r, dict):
        return ["not an object"]
    for k in r:
        if k not in KEYS:
            problems.append(f"unexpected field {k}")
    for k, t in KEYS.items():
        if k not in r:
            problems.append(f"missing {k}")
        elif t is int and (isinstance(r[k], bool) or not isinstance(r[k], int)):
            problems.append(f"{k} must be an integer")
        elif t is bool and not isinstance(r[k], bool):
            problems.append(f"{k} must be a boolean")
        elif t in (str, list) and not isinstance(r[k], t):
            problems.append(f"{k} must be a {t.__name__}")
    if r.get("denial_type") not in ("claim", "prior_authorization", "benefit", "other"):
        problems.append("bad denial_type")
    for k in ("deadline_date", "letter_date"):
        v = r.get(k)
        if isinstance(v, str) and v:
            if not DATE_RE.match(v):
                problems.append(f"{k} not YYYY-MM-DD")
            else:
                try:
                    datetime.strptime(v, "%Y-%m-%d")
                except ValueError:
                    problems.append(f"{k} is not a real date")
    for k in ("reference_ids", "evidence_needed", "questions_to_ask"):
        if isinstance(r.get(k), list) and not all(isinstance(x, str) for x in r[k]):
            problems.append(f"{k} must contain strings")
    if isinstance(r.get("reason_quote"), str) and not r["reason_quote"].strip():
        problems.append("reason_quote is empty")
    return problems


def _norm(s: str) -> str:
    return " ".join(s.split()).lower().strip('"\'')


def quotes_in_letter(r: Dict[str, Any], letter: str) -> List[str]:
    """Names of quoted fields whose text is not found verbatim in the letter."""
    n = _norm(letter); bad = []
    for k in ("reason_quote", "deadline_quote", "appeal_channel"):
        q = _norm(r.get(k, ""))
        if q and q not in n:
            bad.append(k)
    for rid in r.get("reference_ids", []):
        if _norm(rid) and _norm(rid) not in n:
            bad.append(f"reference_ids:{rid}")
    return bad


def compute_deadline(r: Dict[str, Any], received_on: date) -> Dict[str, Any]:
    """The appeal-by date, computed in code from what the letter states, with the basis shown."""
    if r.get("deadline_date"):
        return {"appeal_by": r["deadline_date"], "basis": "explicit date in the letter"}
    days = int(r.get("deadline_days") or 0)
    if days > 0:
        start = date.fromisoformat(r["letter_date"]) if r.get("letter_date") else received_on
        basis = f"{days} days from the letter date {start.isoformat()}" if r.get("letter_date") else f"{days} days from the date you received it ({start.isoformat()})"
        return {"appeal_by": (start + timedelta(days=days)).isoformat(), "basis": basis}
    return {"appeal_by": "", "basis": "the letter does not state a deadline; ask the insurer in writing and note the date you asked"}


def analyze(client: ChatClient, letter: str, received_on: str) -> Dict[str, Any]:
    date.fromisoformat(received_on)
    r = client.chat_json(SYSTEM, f"Date the letter was received: {received_on}\n\nLetter:\n\"\"\"\n{letter.strip()}\n\"\"\"")
    problems = validate(r)
    if problems:
        raise ValueError("model output rejected: " + "; ".join(problems))
    bad = quotes_in_letter(r, letter)
    if bad:
        raise ValueError("model output rejected: not found verbatim in the letter: " + ", ".join(bad))
    r["deadline"] = compute_deadline(r, date.fromisoformat(received_on))
    return r


def appeal_letter(r: Dict[str, Any], name: str, insurer: str, extra_facts: str = "") -> str:
    """A draft the person edits and sends; built from the extracted facts only."""
    refs = ", ".join(r.get("reference_ids", [])) or "[reference number from the letter]"
    lines = [f"To: {insurer}, Appeals Department", f"From: {name}", f"Re: Appeal of denial, reference {refs}", "",
             f"I am writing to formally appeal the decision described in your letter{(' dated ' + r['letter_date']) if r.get('letter_date') else ''}.",
             f"Your letter gives the following reason: \"{r['reason_quote']}\"", "",
             "I disagree with this decision for the following reasons:", "[State why the reason does not apply, in your own words.]"]
    if extra_facts.strip():
        lines += ["", extra_facts.strip()]
    if r.get("evidence_needed"):
        lines += ["", "Enclosed with this appeal:"] + [f"- {e}" for e in r["evidence_needed"]]
    lines += ["", "Please review this appeal and respond in writing. If the denial is upheld, please provide the specific policy language relied on"
              + (" and the instructions for an independent external review." if r.get("external_review_available") else "."),
              "", "Sincerely,", name]
    return "\n".join(lines)
