"""AppealPal web app: one page, one JSON API, standard library only."""
from __future__ import annotations

import json
import os
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .analyze import analyze, appeal_letter
from .llm import ChatClient, LLMError

MAX_CHARS = 15000

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AppealPal</title>
<style>
body{font:17px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1c2230}
header{background:#1f3a5f;color:#fff;padding:18px 24px}header h1{margin:0;font-size:22px}header p{margin:4px 0 0;opacity:.85}
main{max-width:960px;margin:0 auto;padding:16px}
.card{background:#fff;border:1px solid #dde3ec;border-radius:12px;padding:18px;margin-bottom:14px}
label{display:block;font-weight:600;margin-top:10px}input,textarea{font:inherit;padding:10px;border:1px solid #cbd5e1;border-radius:8px;width:100%;box-sizing:border-box}
button{background:#1f6feb;color:#fff;border:0;border-radius:8px;padding:12px 18px;font:inherit;font-size:17px;cursor:pointer;margin-top:12px}button.ghost{background:#e6ecf5;color:#1c2230}
.big{font-size:28px;font-weight:700}.deadline{background:#fff4d6;border-left:6px solid #f59e0b;padding:12px 14px;border-radius:8px;margin:10px 0}
.quote{border-left:6px solid #94a3b8;padding:10px 14px;background:#f8fafc;border-radius:8px;margin:8px 0;font-style:italic}
.err{background:#fde8e8;color:#9b1c1c;padding:10px;border-radius:8px}.muted{color:#64748b;font-size:14px}
ul{padding-left:22px}li{margin:6px 0}pre{white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px;font:15px/1.5 Menlo,monospace}
</style></head><body>
<header><h1>AppealPal</h1><p>A denial letter in, a plan to appeal out. Plain language, the real deadline, the evidence to gather, and a letter you can edit and send.</p></header>
<main>
<div class="card"><label for="letter">Paste the denial letter (insurance claim, prior authorisation, or benefit)</label>
<textarea id="letter" rows="10" placeholder="Paste the full text of the letter here. Nothing you paste leaves this server except the call to the language model."></textarea>
<label for="received">Date you received it</label><input id="received" type="date">
<button onclick="go()">Explain this letter</button> <button class="ghost" onclick="sample()">Try a sample letter</button>
<p class="muted">AppealPal explains and organises. It does not give legal or medical advice, and it never invents a date: every deadline shown is quoted from your letter.</p>
<div id="out"></div></div>
<div id="result"></div>
</main>
<script>
const HDR={'content-type':'application/json','x-appealpal':'ui'};let last=null;
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
document.getElementById('received').value=new Date().toISOString().slice(0,10);
async function sample(){const r=await fetch('/api/sample').then(r=>r.json());document.getElementById('letter').value=r.letter}
async function go(){const o=document.getElementById('out');o.innerHTML='<p class="muted">Reading the letter...</p>';
const r=await fetch('/api/analyze',{method:'POST',headers:HDR,body:JSON.stringify({letter:document.getElementById('letter').value,received_on:document.getElementById('received').value})}).then(r=>r.json());
if(r.error){o.innerHTML=`<div class="err">${esc(r.error)}</div>`;return}o.innerHTML='';last=r;render(r)}
function render(r){const d=r.deadline;let h=`<div class="card"><div class="muted">What the letter says</div><div class="big">${esc(r.reason_plain)}</div><div class="quote">"${esc(r.reason_quote)}"</div>
<div class="deadline"><b>Appeal by: ${esc(d.appeal_by||'not stated')}</b><br><span class="muted">${esc(d.basis)}</span>${r.deadline_quote?`<div class="quote">"${esc(r.deadline_quote)}"</div>`:''}</div>
${r.appeal_channel?`<p><b>How to appeal (from the letter):</b> ${esc(r.appeal_channel)}</p>`:''}
${r.external_review_available?'<p><b>The letter mentions an independent external review</b> if the internal appeal fails.</p>':''}
${r.reference_ids.length?`<p class="muted">Reference numbers to quote: ${r.reference_ids.map(esc).join(', ')}</p>`:''}</div>`;
h+=`<div class="card"><h3>Evidence to gather</h3><ul>${r.evidence_needed.map(e=>`<li>${esc(e)}</li>`).join('')||'<li>None suggested</li>'}</ul><h3>Questions to ask</h3><ul>${r.questions_to_ask.map(e=>`<li>${esc(e)}</li>`).join('')||'<li>None suggested</li>'}</ul></div>`;
h+=`<div class="card"><h3>Draft appeal letter</h3><label>Your name</label><input id="name" placeholder="Alex Example"><label>Insurer or agency</label><input id="insurer" placeholder="Example Health Plan"><label>Anything else you want to say (optional)</label><textarea id="extra" rows="3"></textarea><button onclick="draft()">Build the draft</button><div id="draft"></div></div>`;
document.getElementById('result').innerHTML=h}
async function draft(){const r=await fetch('/api/letter',{method:'POST',headers:HDR,body:JSON.stringify({analysis:last,name:document.getElementById('name').value,insurer:document.getElementById('insurer').value,extra:document.getElementById('extra').value})}).then(r=>r.json());document.getElementById('draft').innerHTML=r.error?`<div class="err">${esc(r.error)}</div>`:`<pre>${esc(r.letter)}</pre>`}
</script></body></html>"""


def make_handler(llm: Optional[ChatClient], sample_letter: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            pass

        def _json(self, code: int, payload: Any) -> None:
            b = json.dumps(payload).encode("utf-8"); self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self) -> None:
            p = urlparse(self.path).path
            if p == "/":
                b = PAGE.encode("utf-8"); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            if p == "/healthz":
                return self._json(200, {"ok": True, "model": llm.model if llm else None})
            if p == "/api/sample":
                return self._json(200, {"letter": sample_letter})
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.headers.get("X-AppealPal") != "ui":
                return self._json(403, {"error": "missing X-AppealPal header"})
            n = int(self.headers.get("Content-Length", "0"))
            if n > MAX_CHARS * 4:
                return self._json(413, {"error": "too large"})
            try:
                body: Dict[str, Any] = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad JSON"})
            p = urlparse(self.path).path
            if p == "/api/analyze":
                letter = str(body.get("letter", ""))
                if not letter.strip():
                    return self._json(400, {"error": "paste the letter first"})
                if len(letter) > MAX_CHARS:
                    return self._json(400, {"error": f"letter is over {MAX_CHARS} characters"})
                if llm is None:
                    return self._json(503, {"error": "no language model configured on this server"})
                try:
                    return self._json(200, analyze(llm, letter, str(body.get("received_on") or date.today().isoformat())))
                except (LLMError, ValueError) as e:
                    return self._json(422, {"error": str(e)})
            if p == "/api/letter":
                a = body.get("analysis")
                if not isinstance(a, dict) or not isinstance(a.get("reason_quote"), str):
                    return self._json(400, {"error": "analyse a letter first"})
                return self._json(200, {"letter": appeal_letter(a, str(body.get("name") or "[Your name]")[:100],
                                                                str(body.get("insurer") or "[Insurer]")[:100], str(body.get("extra", ""))[:2000])})
            self._json(404, {"error": "not found"})
    return H


def serve(host: str, port: int, llm: Optional[ChatClient], sample_letter: str) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("APPEALPAL_PUBLIC") != "1":
        raise SystemExit("set APPEALPAL_PUBLIC=1 to bind beyond loopback")
    return ThreadingHTTPServer((host, port), make_handler(llm, sample_letter))


def main() -> None:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"))
    from letters import CLAIM_DENIAL
    llm = ChatClient.from_env() if os.environ.get("LLM_API_KEY") else None
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8810"))
    httpd = serve(host, port, llm, CLAIM_DENIAL)
    print(f"AppealPal at http://{host}:{port}  model={llm.model if llm else 'NOT CONFIGURED'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
