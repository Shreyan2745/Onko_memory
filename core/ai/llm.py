"""Small Groq helper shared by the AI modules. Owner: Shreyan.

`chat_json()` asks for a JSON object and survives the usual LLM failure modes:
code fences, extra prose around the JSON, Groq's `json_validate_failed` 400
errors, and transient API errors (retried with a short backoff).
"""

from __future__ import annotations

import json
import logging
import re
import time

from core import config

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_client = None


def _get_client():
    """Create the Groq client once."""
    global _client
    if _client is None:
        if Groq is None:
            raise RuntimeError("The 'groq' package is not installed. Run: pip install -r requirements.txt")
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing in .env")
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def parse_json_object(raw: str) -> dict:
    """Pull a JSON object out of model output (fences, prose, or a bare list)."""
    text = re.sub(r"```(?:json)?", "", raw or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"No JSON object in model output: {text[:200]!r}")
        data = json.loads(text[start:end + 1])
    if isinstance(data, list):  # model returned the items array directly
        data = {"items": data}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    return data


def _complete(system: str, user: str, json_mode: bool) -> str:
    """One Groq call; returns the raw message text."""
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = _get_client().chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0,
        **kwargs,
    )
    return resp.choices[0].message.content or ""


def chat_json(system: str, user: str) -> dict:
    """Ask the model for a JSON object, retrying on bad JSON or API errors."""
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # If strict JSON mode itself failed (Groq 400 json_validate_failed), retry without it
        # and parse the object out of the plain reply instead.
        json_mode = attempt == 1 or not isinstance(last_err, _JsonModeError)
        try:
            return parse_json_object(_complete(system, user, json_mode))
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
        except Exception as e:  # groq.BadRequestError, rate limits, timeouts
            last_err = _JsonModeError(str(e)) if "json" in str(e).lower() else e
        log.warning("chat_json attempt %d/%d failed: %s", attempt, MAX_ATTEMPTS, last_err)
        time.sleep(0.8 * attempt)
    raise RuntimeError(f"The AI returned an unreadable answer after {MAX_ATTEMPTS} tries: {last_err}")


class _JsonModeError(Exception):
    """Groq rejected its own output in JSON mode."""
