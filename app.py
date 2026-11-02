"""Local web prototype of the pre-save timing check.

    py -3.11 app.py                 http://localhost:8000 (recorded readings first, live Gemini if a key is set)
    py -3.11 app.py --port 8020
    py -3.11 app.py --mode fixed    Lab 3's hand-written readings (simulated model output)

Standard library only. The server pattern (ThreadingHTTPServer with JSON POST handlers) follows the
Lab 4 app supplied with the module; everything behind it is this project's code.
"""
import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from checker import readings, schema, selector
from checker.session import Session

ROOT = Path(__file__).resolve().parent
SCENARIOS = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
EXAMPLES = [{"id": r["id"], "text": r["text"], "about": r["about"]}
            for r in json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))["requests"]]
LOG = ROOT / "logs" / "sessions.jsonl"
SAVED = ROOT / "data" / "saved_rules.json"
SESSIONS = {}
LOCK = threading.Lock()
MODE = "auto"
MAX_REQUEST = 300


def log_event(event):
    line = json.dumps({"time": readings.now(), **event}, ensure_ascii=False)
    with LOCK:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_rule(record):
    with LOCK:
        rules = json.loads(SAVED.read_text(encoding="utf-8")) if SAVED.exists() else []
        rules.append({"time": readings.now(), **record})
        SAVED.write_text(json.dumps(rules, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def meta():
    return {"scope": schema.SCOPE, "examples": EXAMPLES, "budget": selector.BUDGET, "mode": MODE,
            "live": bool(readings.api_key()) and MODE in ("auto", "live")}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/meta":
            self._send(200, meta())
        elif path == "/api/saved":
            self._send(200, json.loads(SAVED.read_text(encoding="utf-8")) if SAVED.exists() else [])
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._send(400, {"error": "the request body is not JSON"})
        if path == "/api/start":
            text = str(data.get("request", "")).strip()
            if not text:
                return self._send(400, {"error": "type a request first"})
            if len(text) > MAX_REQUEST:
                return self._send(400, {"error": f"please keep the request under {MAX_REQUEST} characters"})
            session = Session(readings.generate(text, MODE), SCENARIOS, logger=log_event,
                              driver=self.headers.get("X-Driver", "browser"))
            with LOCK:
                SESSIONS[session.id] = session
            return self._send(200, session.view())
        session = SESSIONS.get(str(data.get("session", "")))
        if session is None:
            return self._send(404, {"error": "this check has expired; please start again"})
        try:
            if path == "/api/answer":
                session.answer(data.get("answer"))
            elif path == "/api/repair":
                session.choose_repair(data.get("choice"))
            elif path == "/api/decide":
                session.decide(str(data.get("choice", "")), store=save_rule)
            else:
                return self._send(404, {"error": "not found"})
        except ValueError as error:
            return self._send(409, {"error": str(error)})
        self._send(200, session.view())

    def log_message(self, *args):
        pass


def main():
    global MODE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mode", choices=["auto", "recorded", "live", "fixed"], default="auto")
    args = parser.parse_args()
    MODE = args.mode
    sys.stdout.reconfigure(encoding="utf-8")
    live = "a Gemini key is set" if readings.api_key() else "no Gemini key (recorded and example requests only)"
    print(f"Pre-save timing check on http://localhost:{args.port}  (mode {MODE}; {live})")
    print("Stop with Ctrl+C.")
    # Threaded, as in the Lab 4 app: an idle browser connection cannot block other requests.
    try:
        ThreadingHTTPServer(("localhost", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
