"""
Hindsight memory layer. Owner: Samprada.

One memory bank per patient: f"{HINDSIGHT_BANK_PREFIX}-patient-{id}".
  - save_entry()  → client.retain()   store what happened (with source, type, time)
  - ask()         → client.reflect()  answer using the patient's memory + directives

If Hindsight is not configured (.env empty), it falls back to a tiny
in-process store so the UI still works during early development.
Docs: https://hindsight.vectorize.io/sdks/python
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading

from core import config
from core.contracts import Entry, Patient

log = logging.getLogger(__name__)

try:
    from hindsight_client import Hindsight
except ImportError:  # package not installed yet
    Hindsight = None  # type: ignore

# ─────────────── Bank identity & safety rules ───────────────

MISSION = (
    "I am OnKo, a cancer-care companion for one patient. I remember the doctor's "
    "approved care plan, reports, the patient's daily check-ins, symptoms, diary "
    "entries and conversations. I help the patient understand what has been "
    "recorded and I help the care team see what happened between visits. "
    "The doctor makes all clinical decisions."
)

# Hard rules enforced by Hindsight during reflect().
# Shreyan tests these with tricky questions and proposes edits.
DIRECTIVES: dict[str, str] = {
    "Cite sources": (
        "When stating a patient-specific fact, say who recorded it and when "
        "(e.g. 'from Dr. Mehta's plan, 20 Sep' or 'you logged this on 24 Sep')."
    ),
    "No lab interpretation": (
        "Never say whether a lab value is normal, low, high, good or bad, and never "
        "infer a condition from it. You may repeat the recorded value and date, then "
        "say the doctor will interpret it."
    ),
    "No medication changes": (
        "Never advise starting, stopping, skipping, doubling or changing any medicine "
        "or dose. Repeat what the doctor prescribed and suggest asking the care team."
    ),
    "No diagnosis": (
        "Never diagnose, predict prognosis, or assign a risk level. You may point out "
        "patterns in what was recorded (e.g. 'you reported nausea after the last two cycles')."
    ),
    "Honest gaps": (
        "If the information is not in memory, say so plainly. Never invent medicines, "
        "dates, doses or results."
    ),
    "Plain language": "Use short, simple, warm sentences the patient can understand.",
}

# ─────────────── Client ───────────────

_client = None
_offline_store: dict[str, list[Entry]] = {}
_ready_banks: set[str] = set()


def _get_client():
    global _client
    if _client is None and Hindsight is not None and config.HINDSIGHT_BASE_URL:
        _client = Hindsight(base_url=config.HINDSIGHT_BASE_URL, api_key=config.HINDSIGHT_API_KEY, timeout=60.0)
    return _client


# The Hindsight client's sync methods break when an event loop is already running in
# the calling thread (which happens inside Streamlit): "This event loop is already running".
# So every call goes through ONE background thread with its own event loop, using the
# client's async methods. Same thread + same loop every time = no loop conflicts.
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _call(method: str, **kwargs):
    """Run client.<method>(**kwargs) (an async 'a...' method) on the Hindsight thread."""
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="hindsight", daemon=True).start()
    coro = getattr(_get_client(), method)(**kwargs)
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=120)


@atexit.register
def close() -> None:
    """Close the Hindsight HTTP session on exit (stops 'Unclosed client session' warnings)."""
    global _client
    if _client is not None:
        try:
            if _loop is not None:
                _call("aclose")
            else:
                _client.close()
        except Exception:
            pass
        _client = None


def is_online() -> bool:
    """True if Hindsight is configured (not the offline fallback)."""
    return _get_client() is not None


def bank_id_for(patient_id: int) -> str:
    return f"{config.HINDSIGHT_BANK_PREFIX}-patient-{patient_id}"


def ensure_bank(patient: Patient) -> str:
    """Create the patient's bank + directives once. Safe to call repeatedly."""
    bank_id = bank_id_for(patient.id)
    client = _get_client()
    if client is None or bank_id in _ready_banks:
        return bank_id
    try:
        _call(
            "acreate_bank",
            bank_id=bank_id,
            name=f"OnKo — {patient.name}",
            mission=MISSION,
            disposition={"skepticism": 4, "literalism": 4, "empathy": 4},
            enable_observations=True,  # the "learning" part of the demo
        )
    except Exception as e:  # bank probably exists already
        log.info("create_bank skipped for %s: %s", bank_id, e)
    try:
        resp = _call("alist_directives", bank_id=bank_id)
        existing = {d.name for d in (getattr(resp, "items", None) or resp or [])}
    except Exception:
        existing = set()
    for name, content in DIRECTIVES.items():
        if name not in existing:
            try:
                _call("acreate_directive", bank_id=bank_id, name=name, content=content)
            except Exception as e:
                log.warning("create_directive %s failed: %s", name, e)
    _ready_banks.add(bank_id)
    return bank_id


# ─────────────── Core operations ───────────────

def _format(entry: Entry) -> str:
    when = entry.timestamp.strftime("%d %b %Y, %I:%M %p")
    return f"[{entry.type.value} | recorded by {entry.source.value} | {when}]\n{entry.content}"


def save_entry(entry: Entry) -> None:
    """Store one Entry in the patient's memory bank."""
    bank_id = bank_id_for(entry.patient_id)
    client = _get_client()
    if client is None:
        _offline_store.setdefault(bank_id, []).append(entry)
        return
    _call(
        "aretain",
        bank_id=bank_id,
        content=_format(entry),
        context=entry.type.value,
        timestamp=entry.timestamp,
        metadata={"source": entry.source.value, "type": entry.type.value, **entry.metadata},
    )


def ask(patient_id: int, question: str, context: str = "") -> str:
    """Answer a question using the patient's memory (Hindsight reflect)."""
    bank_id = bank_id_for(patient_id)
    client = _get_client()
    if client is None:
        recent = _offline_store.get(bank_id, [])[-5:]
        lines = "\n".join(f"- {_format(e)}" for e in recent) or "- (nothing stored yet)"
        return f"⚠️ Offline mode (Hindsight not configured). Last things stored:\n{lines}"
    answer = _call("areflect", bank_id=bank_id, query=question, budget="mid", context=context or None, apply_all_directives=True)
    return answer.text