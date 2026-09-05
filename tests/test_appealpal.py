import json, os, sys, threading, urllib.request, urllib.error
from datetime import date
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path[:0] = [ROOT, os.path.join(ROOT, "fixtures")]
from fake_llm import FakeLLM  # noqa
from letters import CLAIM_DENIAL, PRIOR_AUTH_DENIAL, BENEFIT_DENIAL_DATED, NO_DEADLINE_DENIAL, SAMPLES  # noqa
from appealpal.analyze import analyze, appeal_letter, compute_deadline, validate  # noqa
from appealpal.llm import ChatClient, LLMError  # noqa
from appealpal.web import serve, DEMO_BANNER_TEXT, DEMO_UNMATCHED_MESSAGE  # noqa


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


def _post(base, path, body, hdr=True):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-AppealPal": "ui"} if hdr else {})})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())


def test_web_end_to_end(fake):
    llm = ChatClient("k", fake.base_url, "m", allow_local=True)
    httpd = serve("127.0.0.1", 0, llm, SAMPLES); threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert _post(base, "/api/analyze", {"letter": CLAIM_DENIAL}, hdr=False)[0] == 403
        code, r = _post(base, "/api/analyze", {"letter": CLAIM_DENIAL, "received_on": "2026-08-25"})
        assert code == 200 and r["deadline"]["appeal_by"] == "2027-02-16"
        code, l = _post(base, "/api/letter", {"analysis": r, "name": "Alex Example", "insurer": "Example Health Plan"})
        assert code == 200 and "appeal" in l["letter"].lower()
        assert _post(base, "/api/analyze", {"letter": "MALFORMED-TEST", "received_on": "2026-08-25"})[0] == 422
        samples = json.loads(urllib.request.urlopen(base + "/api/samples").read())
        assert len(samples) >= 4 and any(s["text"] == CLAIM_DENIAL for s in samples)
        assert "AppealPal" in urllib.request.urlopen(base + "/").read().decode()
        health = json.loads(urllib.request.urlopen(base + "/healthz").read())
        assert health == {"ok": True, "mode": "real", "model": "m", "rate_limit_per_minute": 30}
    finally:
        httpd.shutdown(); httpd.server_close()


def test_demo_mode_serves_banner_and_canned_samples_but_explains_arbitrary_text(fake):
    llm = ChatClient("k", fake.base_url, "m", allow_local=True)
    httpd = serve("127.0.0.1", 0, llm, SAMPLES, demo=True); threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert DEMO_BANNER_TEXT in page
        for s in SAMPLES:
            assert s["label"] in page  # every sample is offered as a "Load sample" button
        health = json.loads(urllib.request.urlopen(base + "/healthz").read())
        assert health["mode"] == "demo"
        # a recognized sample letter still gets a real, quote-checked analysis
        code, r = _post(base, "/api/analyze", {"letter": CLAIM_DENIAL, "received_on": "2026-08-25"})
        assert code == 200 and r["deadline"]["appeal_by"] == "2027-02-16"
        # arbitrary pasted text gets a friendly explanation, never a fabricated analysis
        code, r = _post(base, "/api/analyze", {"letter": "My insurer denied my claim for reasons unknown.", "received_on": "2026-08-25"})
        assert code == 200 and r == {"demo_notice": True, "message": DEMO_UNMATCHED_MESSAGE}
    finally:
        httpd.shutdown(); httpd.server_close()


def test_rate_limit_blocks_after_the_per_ip_budget(fake):
    llm = ChatClient("k", fake.base_url, "m", allow_local=True)
    httpd = serve("127.0.0.1", 0, llm, SAMPLES, rate_limit_per_minute=2); threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        codes = [_post(base, "/api/analyze", {"letter": CLAIM_DENIAL, "received_on": "2026-08-25"})[0] for _ in range(3)]
        assert codes == [200, 200, 429]
        req = urllib.request.Request(base + "/api/analyze", data=b"{}", method="POST", headers={"X-AppealPal": "ui"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 429 and e.value.headers.get("Retry-After") == "60"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_benefit_denial_with_explicit_appeal_date(llm):
    r = analyze(llm, BENEFIT_DENIAL_DATED, "2026-08-20")
    assert r["denial_type"] == "benefit" and r["reason_quote"] in BENEFIT_DENIAL_DATED
    assert r["deadline"] == {"appeal_by": "2026-10-30", "basis": "explicit date in the letter"}


def test_benefit_denial_with_no_stated_deadline(llm):
    r = analyze(llm, NO_DEADLINE_DENIAL, "2026-08-12")
    assert r["denial_type"] == "benefit" and r["reason_quote"] in NO_DEADLINE_DENIAL
    assert r["deadline"] == {"appeal_by": "", "basis": "the letter does not state a deadline; ask the insurer in writing and note the date you asked"}


def test_days_from_receipt_deadline_edge_case():
    # letter states a day count but no letter_date at all: the clock runs from the date received
    r = {"deadline_date": "", "deadline_days": 45, "letter_date": ""}
    d = compute_deadline(r, date(2026, 9, 1))
    assert d == {"appeal_by": "2026-10-16", "basis": "45 days from the date you received it (2026-09-01)"}
