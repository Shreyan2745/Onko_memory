"""
Doctor's free-text care plan → structured CarePlanItems. Owner: Shreyan.

Rule (from the OnKo spec): the AI may only STRUCTURE what the doctor wrote.
It must never invent a medicine, dose, test or date. The doctor reviews and
approves every item in the UI before anything is saved.

Pipeline:  LLM (JSON)  →  clean_items()  →  doctor review table
clean_items() is pure Python and fixes what LLMs typically get wrong:
kind synonyms, free-text timings, odd date formats, reversed date ranges,
duplicates, and anything the model added that isn't in the doctor's text.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from core import config
from core.ai.llm import chat_json
from core.contracts import TIME_SLOTS, CarePlanItem, ItemKind

SYSTEM_PROMPT = f"""You convert a doctor's care-plan text into structured items.
Return JSON: {{"items": [ {{
  "kind": one of {[k.value for k in ItemKind]},
  "name": string,             // medicine / test / appointment / treatment / instruction name
  "dose": string,             // "" if none
  "timings": [string],        // subset of {TIME_SLOTS}; [] for "as needed" or one-off events
  "start_date": "YYYY-MM-DD", // event date for tests/appointments/treatments
  "end_date": "YYYY-MM-DD" or "",
  "notes": string             // e.g. "after food", "if nausea"
}} ]}}
Rules:
- Only include what the doctor explicitly wrote. Never add medicines, doses, tests or dates.
- Copy medicine and test names exactly as the doctor spelled them.
- "twice daily"/"BD" = ["morning","evening"]; "thrice daily"/"TDS" = ["morning","afternoon","night"];
  "once daily"/"OD" = ["morning"] unless a time is given; "at night"/"bedtime"/"HS" = ["night"];
  "if needed"/"SOS"/"PRN"/"if nausea" = [] and put the condition in notes.
- Convert relative dates ("days 1-14", "in 5 days", "next Monday", "on 3 Oct") into absolute
  dates using TODAY. "Days 1-14" of a cycle starting today means start_date=TODAY,
  end_date=TODAY+13 days. A date without a year is in the next occurrence of that date.
- Medicines with no dates start TODAY with end_date "".
- If an event date is missing or unclear, use "" rather than guessing.
"""

# ─────────────── Normalization tables ───────────────

_KIND_ALIASES = {
    "medication": ItemKind.MEDICATION, "medicine": ItemKind.MEDICATION, "drug": ItemKind.MEDICATION,
    "tablet": ItemKind.MEDICATION, "capsule": ItemKind.MEDICATION, "injection": ItemKind.MEDICATION,
    "test": ItemKind.TEST, "lab": ItemKind.TEST, "lab test": ItemKind.TEST, "investigation": ItemKind.TEST,
    "scan": ItemKind.TEST, "blood test": ItemKind.TEST, "imaging": ItemKind.TEST,
    "appointment": ItemKind.APPOINTMENT, "visit": ItemKind.APPOINTMENT, "follow-up": ItemKind.APPOINTMENT,
    "follow up": ItemKind.APPOINTMENT, "review": ItemKind.APPOINTMENT, "consultation": ItemKind.APPOINTMENT,
    "treatment": ItemKind.TREATMENT, "chemo": ItemKind.TREATMENT, "chemotherapy": ItemKind.TREATMENT,
    "infusion": ItemKind.TREATMENT, "radiation": ItemKind.TREATMENT, "radiotherapy": ItemKind.TREATMENT,
    "procedure": ItemKind.TREATMENT, "surgery": ItemKind.TREATMENT,
    "instruction": ItemKind.INSTRUCTION, "advice": ItemKind.INSTRUCTION, "diet": ItemKind.INSTRUCTION,
}

_TIMING_ALIASES = {
    "morning": ["morning"], "am": ["morning"], "breakfast": ["morning"],
    "afternoon": ["afternoon"], "noon": ["afternoon"], "lunch": ["afternoon"],
    "evening": ["evening"], "pm": ["evening"], "dinner": ["evening"],
    "night": ["night"], "bedtime": ["night"], "hs": ["night"], "at night": ["night"],
    "daily": ["daily"], "once daily": ["morning"], "once a day": ["morning"], "od": ["morning"],
    "twice daily": ["morning", "evening"], "twice a day": ["morning", "evening"],
    "bd": ["morning", "evening"], "bid": ["morning", "evening"],
    "thrice daily": ["morning", "afternoon", "night"], "three times a day": ["morning", "afternoon", "night"],
    "tds": ["morning", "afternoon", "night"], "tid": ["morning", "afternoon", "night"],
}
_AS_NEEDED = {"sos", "prn", "as needed", "if needed", "when needed", "as required"}

_SLOT_ORDER = {s: i for i, s in enumerate(TIME_SLOTS)}
_ONE_DAY_KINDS = (ItemKind.TEST, ItemKind.APPOINTMENT, ItemKind.TREATMENT)
_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                 "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y")
_NO_YEAR_FORMATS = ("%d %b", "%d %B", "%b %d", "%B %d", "%d/%m")

UNVERIFIED_NOTE = "⚠ not found in the doctor's text, please check"


def to_kind(value: object) -> ItemKind:
    """Map any kind label the model uses to an ItemKind (default: instruction)."""
    key = str(value or "").strip().lower()
    return _KIND_ALIASES.get(key, ItemKind.INSTRUCTION)


def to_timings(value: object) -> list[str]:
    """Free-text timings (list or string) → standard slots in day order."""
    parts = value if isinstance(value, list) else re.split(r"[,/;+&]| and ", str(value or ""))
    slots: list[str] = []
    for part in parts:
        key = str(part).strip().lower().replace("-", " ")
        if not key or key in _AS_NEEDED:
            continue
        for slot in _TIMING_ALIASES.get(key, [key] if key in _SLOT_ORDER else []):
            if slot not in slots:
                slots.append(slot)
    return sorted(slots, key=_SLOT_ORDER.get)


def to_iso_date(value: object, today: str) -> str:
    """Common date formats → 'YYYY-MM-DD'; dates without a year take the next occurrence."""
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value or "").strip())
    if not text:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:  # unpadded ISO like 2026-9-3
        y, m, d = (int(x) for x in text.split("-"))
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        pass
    base = date.fromisoformat(today)
    for fmt in _NO_YEAR_FORMATS:
        try:
            parsed = datetime.strptime(f"{text} {base.year}", f"{fmt} %Y").date()
        except ValueError:
            continue
        if parsed < base:
            parsed = parsed.replace(year=base.year + 1)
        return parsed.isoformat()
    return ""


def _in_text(name: str, source_text: str) -> bool:
    """True if the item's main word appears in the doctor's text (catches invented items)."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) >= 3]
    haystack = source_text.lower()
    return not words or any(w in haystack for w in words)


def clean_items(raw_items: list[dict], today: str, source_text: str = "") -> list[CarePlanItem]:
    """Normalize raw LLM items into valid, de-duplicated CarePlanItems."""
    items: list[CarePlanItem] = []
    seen: set[tuple] = set()
    for raw in raw_items or []:
        if not isinstance(raw, dict):
            continue
        name = " ".join(str(raw.get("name") or "").split())
        if not name:
            continue
        kind = to_kind(raw.get("kind"))
        timings = to_timings(raw.get("timings"))
        start = to_iso_date(raw.get("start_date"), today)
        end = to_iso_date(raw.get("end_date"), today)
        notes = " ".join(str(raw.get("notes") or "").split())

        if kind in (ItemKind.MEDICATION, ItemKind.INSTRUCTION):
            start = start or today
        else:
            timings = []          # one-off events are not ticked per time slot
            end = ""              # and happen on a single day
        if end and start and end < start:
            start, end = end, start  # reversed range typo

        if source_text and not _in_text(name, source_text):
            notes = f"{notes} · {UNVERIFIED_NOTE}".strip(" ·")

        key = (kind, name.lower(), str(raw.get("dose") or "").strip().lower(), tuple(timings), start, end)
        if key in seen:
            continue
        seen.add(key)
        items.append(CarePlanItem(kind, name, " ".join(str(raw.get("dose") or "").split()),
                                  timings, start, end, notes))
    return items


_SAMPLE = [
    {"kind": "medication", "name": "Capecitabine", "dose": "1500 mg", "timings": ["morning", "evening"], "notes": "after food"},
    {"kind": "test", "name": "CBC", "notes": "stub data"},
]


def extract_care_plan(text: str, today: str) -> list[CarePlanItem]:
    """Doctor's plain-text plan → cleaned CarePlanItems for the doctor to review."""
    if config.USE_STUBS:
        return clean_items(_SAMPLE, today)
    if not text.strip():
        return []
    data = chat_json(SYSTEM_PROMPT, f"TODAY: {today} ({date.fromisoformat(today):%A})\n\nDOCTOR'S PLAN:\n{text}")
    return clean_items(data.get("items", []), today, source_text=text)
