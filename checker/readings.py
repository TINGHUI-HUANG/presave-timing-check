"""Candidate readings for a request: recorded model output, a live Gemini call, or Lab 3's
hand-written readings.

Context assembly (Lecture 10): a call sends two parts only, the designer's versioned instruction
(prompts/readings_<version>.txt) and the person's request. The response schema fixes the reply's
shape; its vocabulary is checked afterwards in schema.check, because a schema guarantees shape,
not truth (Lecture 9).

The key is read from the environment or from .env and travels only in the x-goog-api-key header.
It is never logged, recorded or shown.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import schema, simulator

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPT_VERSION = "v1"
ENDPOINTS = {
    "gemini-api": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    "vertex-express": "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent",
}
MODEL_CANDIDATES = ("gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash-lite")
TIMEOUT = 45
TEMPERATURE = 0.4

_RULE = {"type": "OBJECT", "properties": {
    "when": {"type": "ARRAY", "items": {"type": "STRING"}},
    "if": {"type": "ARRAY", "items": {"type": "STRING"}},
    "device": {"type": "STRING"},
    "do": {"type": "STRING"}},
    "required": ["when", "if", "device", "do"]}
RESPONSE_SCHEMA = {"type": "OBJECT", "properties": {
    "unsupported": {"type": "STRING"},
    "readings": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "label": {"type": "STRING"},
        "rules": {"type": "ARRAY", "items": _RULE}},
        "required": ["label", "rules"]}}},
    "required": ["unsupported", "readings"]}


class GeneratorError(Exception):
    """The model could not be reached or returned nothing usable."""


@dataclass
class Generated:
    request: str
    source: dict                 # kind: recorded / live / fixed / none, plus model, endpoint, prompt version, time
    context: dict                # what was sent to the model (for a recording: what was sent when it was made)
    raw_text: str = ""
    readings: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    error: str = ""              # "", "no_source", "model_failed" or "unusable"
    error_detail: str = ""

    def to_log(self):
        return asdict(self)


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalise(text):
    text = text.replace("’", "'").replace("‘", "'").strip().lower()
    return re.sub(r"\s+", " ", text).rstrip(" .!?")


def load_env(path=None):
    """Read KEY=value lines from .env into the environment, without overriding what is already set."""
    path = Path(path) if path else ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name and value and name not in os.environ:
            os.environ[name] = value


def api_key():
    load_env()
    return os.environ.get("GEMINI_API_KEY", "").strip()


def live_settings():
    """(endpoint, model): from the environment or .env, else from the last successful --check."""
    load_env()
    saved = {}
    path = DATA / "live_config.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
    endpoint = os.environ.get("GEMINI_ENDPOINT") or saved.get("endpoint") or "gemini-api"
    model = os.environ.get("GEMINI_MODEL") or saved.get("model") or MODEL_CANDIDATES[0]
    return endpoint, model


def instruction(version=PROMPT_VERSION):
    return (ROOT / "prompts" / f"readings_{version}.txt").read_text(encoding="utf-8")


def build_context(request, version=PROMPT_VERSION):
    """Select, order and record the context: instruction first, the person's request last."""
    return {"prompt_version": version, "instruction": instruction(version),
            "request": f'Request: "{request.strip()}"'}


def reply_text(payload):
    """The text of the first candidate, skipping any 'thought' parts. Raises GeneratorError if empty."""
    candidates = payload.get("candidates") or []
    if not candidates:
        reason = (payload.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise GeneratorError(f"the model returned no answer ({reason})")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise GeneratorError(f"the model returned no text ({candidates[0].get('finishReason', 'unknown')})")
    return text


def _error_message(error):
    try:
        body = json.loads(error.read().decode("utf-8"))
        return body.get("error", {}).get("message", "")[:200]
    except Exception:
        return ""


def call(context, endpoint, model, key, timeout=TIMEOUT):
    """One generateContent call. Returns (text, meta). Raises GeneratorError."""
    body = {
        "systemInstruction": {"parts": [{"text": context["instruction"]}]},
        "contents": [{"role": "user", "parts": [{"text": context["request"]}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA,
                             "temperature": TEMPERATURE},
    }
    request = urllib.request.Request(
        ENDPOINTS[endpoint].format(model=model), data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise GeneratorError(f"HTTP {error.code}: {_error_message(error) or error.reason}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise GeneratorError(f"could not reach the model service ({getattr(error, 'reason', error)})") from None
    except json.JSONDecodeError:
        raise GeneratorError("the service sent a reply that is not JSON") from None
    candidates = payload.get("candidates") or [{}]
    meta = {"model_version": payload.get("modelVersion"), "finish_reason": candidates[0].get("finishReason"),
            "usage": payload.get("usageMetadata")}
    return reply_text(payload), meta


def interpret(request, text, source, context):
    """Parse and check a reply. Problems make it unusable; unsupported terms make it a decline."""
    generated = Generated(request, source, context, raw_text=text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        generated.problems = ["the reply is not valid JSON"]
        generated.error, generated.error_detail = "unusable", "the reply is not valid JSON"
        return generated
    result = schema.check(payload)
    generated.readings, generated.unsupported = result["readings"], result["unsupported"]
    generated.problems, generated.notes = result["problems"], result["notes"]
    if not generated.problems and not generated.unsupported:
        for reading in generated.readings:
            if simulator.conflicts(reading):
                generated.problems.append(f"{reading['id']} has conflicting on and off actions for the same event and conditions")
    if generated.problems:
        generated.error, generated.error_detail = "unusable", "; ".join(generated.problems)
    elif not generated.readings and not generated.unsupported:
        generated.error, generated.error_detail = "unusable", "the reply contains no readings"
    return generated


def recordings():
    path = DATA / "recorded_readings.json"
    return json.loads(path.read_text(encoding="utf-8")).get("recordings", []) if path.exists() else []


def find_recording(request, version=PROMPT_VERSION):
    """The latest successful recording of this request, preferring the current prompt version."""
    wanted = normalise(request)
    matches = [r for r in recordings() if normalise(r["request"]) == wanted and not r.get("error")]
    same_version = [r for r in matches if r.get("prompt_version") == version]
    return (same_version or matches or [None])[-1]


def find_fixed(request):
    path = DATA / "fixed_readings.json"
    wanted = normalise(request)
    for item in json.loads(path.read_text(encoding="utf-8"))["requests"]:
        if normalise(item["request"]) == wanted:
            return item["reply"]
    return None


def generate(request, mode="auto"):
    """mode: "auto" (a recording if there is one, else a live call if a key is set, else Lab 3's
    hand-written readings if the request has them), "recorded", "live" or "fixed" (hand-written,
    labelled simulated). A failed live call is reported, never replaced by another source."""
    if mode == "fixed":
        reply = find_fixed(request)
        source = {"kind": "fixed", "note": "hand-written in Lab 3 (simulated model output)"}
        if reply is None:
            return Generated(request, source, {}, error="no_source", error_detail="no hand-written readings for this request")
        return interpret(request, json.dumps(reply), source, {})
    if mode in ("auto", "recorded"):
        record = find_recording(request)
        if record:
            source = {"kind": "recorded", "model": record["model"], "model_version": record.get("model_version"),
                      "endpoint": record["endpoint"], "prompt_version": record["prompt_version"], "time": record["time"]}
            return interpret(request, record["raw_text"], source, record["context"])
        if mode == "recorded":
            return Generated(request, {"kind": "none"}, {}, error="no_source", error_detail="no recording of this request")
    context = build_context(request)
    key = api_key()
    if not key:
        if mode == "auto" and find_fixed(request) is not None:
            return generate(request, mode="fixed")   # Lab 3's hand-written readings, labelled simulated
        return Generated(request, {"kind": "none"}, context, error="no_source",
                         error_detail="no recording of this request and no Gemini key is set")
    endpoint, model = live_settings()
    source = {"kind": "live", "endpoint": endpoint, "model": model, "prompt_version": context["prompt_version"],
              "time": now()}
    started = time.time()
    try:
        text, meta = call(context, endpoint, model, key)
    except GeneratorError as error:
        source["latency_s"] = round(time.time() - started, 1)
        return Generated(request, source, context, error="model_failed", error_detail=str(error))
    source.update(latency_s=round(time.time() - started, 1), model_version=meta.get("model_version"))
    return interpret(request, text, source, context)
