"""Loopback fake of an OpenAI-compatible chat endpoint: returns canned analyses for the fixture letters."""
from __future__ import annotations

import json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, List

HERE = os.path.dirname(os.path.abspath(__file__))


class FakeLLM:
    def __init__(self, host="127.0.0.1", port=0):
        with open(os.path.join(HERE, "scenarios.json"), "r", encoding="utf-8") as f:
            scenarios = json.load(f)
        self.requests: List[Any] = []
        server = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, code, payload):
                b = json.dumps(payload).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def do_POST(self):
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    return self._send(401, {"error": "unauthorized"})
                n = int(self.headers.get("Content-Length", "0")); req = json.loads(self.rfile.read(n) or b"{}")
                server.requests.append(req)
                user = next((m["content"] for m in req.get("messages", []) if m.get("role") == "user"), "")
                for sc in scenarios:
                    if sc["match"] in user:
                        content = json.dumps(sc["analysis"]) if "analysis" in sc else sc["raw"]
                        return self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {"total_tokens": 700}})
                self._send(200, {"choices": [{"message": {"role": "assistant", "content": json.dumps({"denial_type": "other", "reason_quote": "", "reason_plain": "", "deadline_quote": "", "deadline_days": 0, "deadline_date": "", "letter_date": "", "appeal_channel": "", "reference_ids": [], "evidence_needed": [], "questions_to_ask": [], "external_review_available": False})}}]})

        self.httpd = ThreadingHTTPServer((host, port), H)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self):
        h, p = self.httpd.server_address[:2]; return f"http://{h}:{p}"

    def start(self): self.thread.start(); return self
    def stop(self): self.httpd.shutdown(); self.httpd.server_close()


if __name__ == "__main__":
    s = FakeLLM(port=int(os.environ.get("PORT", "8798"))).start(); print(f"fake LLM at {s.base_url}")
    try: threading.Event().wait()
    except KeyboardInterrupt: s.stop()
