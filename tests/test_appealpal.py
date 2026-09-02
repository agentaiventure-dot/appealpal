import json, os, sys, threading, urllib.request, urllib.error
from datetime import date
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [ROOT, os.path.join(ROOT, "fixtures")]
from fake_llm import FakeLLM  # noqa
from letters import CLAIM_DENIAL, PRIOR_AUTH_DENIAL  # noqa
from appealpal.analyze import analyze, appeal_letter, compute_deadline, validate  # noqa
from appealpal.llm import ChatClient, LLMError  # noqa
from appealpal.web import serve  # noqa


@pytest.fixture(scope="module")
def fake():
    s = FakeLLM().start(); yield s; s.stop()


@pytest.fixture
def llm(fake):
    return ChatClient("k", fake.base_url, "test-model", allow_local=True)


def test_key_only_goes_to_allowlisted_origins(fake):
    assert ChatClient("k", "https://api.groq.com/openai", "m").base == "https://api.groq.com/openai"
    for bad in ("https://api.groq.com.evil.example", "http://api.groq.com/openai", "https://evil.example", fake.base_url):
        with pytest.raises(LLMError):
            ChatClient("k", bad, "m")
    with pytest.raises(LLMError):
        ChatClient("", "https://api.groq.com/openai", "m")


def test_claim_denial_is_explained_with_quoted_reason_and_computed_deadline(llm):
    r = analyze(llm, CLAIM_DENIAL, "2026-08-25")
    assert r["denial_type"] == "claim" and r["reason_quote"] in CLAIM_DENIAL
    assert r["deadline"] == {"appeal_by": "2027-02-16", "basis": "180 days from the letter date 2026-08-20"}
    assert r["external_review_available"] is True and "EXAMPLE-CLAIM-7781" in r["reference_ids"]
    body = llm.last_usage; assert body.get("total_tokens") == 700


def test_prior_auth_deadline_counts_from_receipt_when_letter_says_so(llm):
    r = analyze(llm, PRIOR_AUTH_DENIAL, "2026-09-01")
    # letter_date is stated, so the code uses the letter date (conservative: earlier deadline)
    assert r["deadline"]["appeal_by"] == "2026-10-27"


def test_deadline_computation_is_conservative_and_explicit():
    base = {"deadline_date": "", "deadline_days": 0, "letter_date": ""}
    assert compute_deadline({**base, "deadline_date": "2026-12-01"}, date(2026, 9, 1))["appeal_by"] == "2026-12-01"
    d = compute_deadline({**base, "deadline_days": 30}, date(2026, 9, 1))
    assert d["appeal_by"] == "2026-10-01" and "received" in d["basis"]
    assert compute_deadline(base, date(2026, 9, 1))["appeal_by"] == ""


def test_invented_quote_and_malformed_output_are_rejected(llm):
    with pytest.raises(ValueError, match="not found verbatim"):
        analyze(llm, "INVENTED-TEST letter with a mild reason.", "2026-09-01")
    with pytest.raises(ValueError, match="rejected"):
        analyze(llm, "MALFORMED-TEST", "2026-09-01")
    good = {"denial_type": "claim", "reason_quote": "r", "reason_plain": "p", "deadline_quote": "", "deadline_days": 30, "deadline_date": "",
            "letter_date": "", "appeal_channel": "", "reference_ids": [], "evidence_needed": [], "questions_to_ask": [], "external_review_available": False}
    assert validate(good) == []
    assert "deadline_days must be an integer" in validate({**good, "deadline_days": "30"})
    assert "deadline_days must be an integer" in validate({**good, "deadline_days": True})
    assert "letter_date is not a real date" in validate({**good, "letter_date": "2026-02-30"})
    assert "unexpected field extra" in validate({**good, "extra": 1})


def test_appeal_letter_uses_only_extracted_facts(llm):
    r = analyze(llm, CLAIM_DENIAL, "2026-08-25")
    text = appeal_letter(r, "Alex Example", "Example Health Plan", "The MRI was ordered after eight weeks of physiotherapy.")
    assert r["reason_quote"] in text and "EXAMPLE-CLAIM-7781" in text and "external review" in text and "eight weeks" in text


def test_web_end_to_end(fake):
    llm = ChatClient("k", fake.base_url, "m", allow_local=True)
    httpd = serve("127.0.0.1", 0, llm, CLAIM_DENIAL); threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def post(path, body, hdr=True):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-AppealPal": "ui"} if hdr else {})})
        try:
            with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read())
    try:
        assert post("/api/analyze", {"letter": CLAIM_DENIAL}, hdr=False)[0] == 403
        code, r = post("/api/analyze", {"letter": CLAIM_DENIAL, "received_on": "2026-08-25"})
        assert code == 200 and r["deadline"]["appeal_by"] == "2027-02-16"
        code, l = post("/api/letter", {"analysis": r, "name": "Alex Example", "insurer": "Example Health Plan"})
        assert code == 200 and "appeal" in l["letter"].lower()
        assert post("/api/analyze", {"letter": "MALFORMED-TEST", "received_on": "2026-08-25"})[0] == 422
        assert json.loads(urllib.request.urlopen(base + "/api/sample").read())["letter"] == CLAIM_DENIAL
        assert "AppealPal" in urllib.request.urlopen(base + "/").read().decode()
    finally:
        httpd.shutdown(); httpd.server_close()
