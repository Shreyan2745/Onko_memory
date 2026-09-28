"""
Turns the approved care plan into the patient's checklist for a given day.
Owner: Samprada.

Handles messy input from AI extraction / doctors:
  - dates in ISO, "20 Sep 2026", "20/09/2026", or unpadded "2026-9-3"
  - timings like "Morning", "twice daily", "bedtime", "BD"
  - the same medicine approved twice (plan revised) → newest approval wins
  - end date before start date (typo) → treated as a single day
"""

from __future__ import annotations

from datetime import date, datetime

from core import db
from core.contracts import CarePlanItem, ChecklistItem, ItemKind

_SLOT_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3, "daily": 4, "": 5}

# Free-text timing → one or more standard slots (TIME_SLOTS in contracts.py)
_TIMING_ALIASES: dict[str, list[str]] = {
    "morning": ["morning"], "am": ["morning"], "breakfast": ["morning"],
    "afternoon": ["afternoon"], "noon": ["afternoon"], "lunch": ["afternoon"],
    "evening": ["evening"], "pm": ["evening"], "dinner": ["evening"],
    "night": ["night"], "bedtime": ["night"], "hs": ["night"],
    "daily": ["daily"], "once daily": ["daily"], "once a day": ["daily"], "od": ["daily"],
    "twice daily": ["morning", "evening"], "twice a day": ["morning", "evening"], "bd": ["morning", "evening"], "bid": ["morning", "evening"],
    "thrice daily": ["morning", "afternoon", "night"], "three times a day": ["morning", "afternoon", "night"],
    "tds": ["morning", "afternoon", "night"], "tid": ["morning", "afternoon", "night"],
}

_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def normalize_date(value: str) -> str:
    """Any common date format → ISO 'YYYY-MM-DD'. Returns '' if empty or unreadable."""
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    try:  # unpadded ISO like 2026-9-3
        y, m, d = (int(x) for x in value.split("-"))
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return ""


def normalize_timings(timings: list[str]) -> list[str]:
    """['Morning', 'twice daily'] → ['morning', 'evening'] (standard slots, no duplicates, in day order)."""
    slots: list[str] = []
    for t in timings or []:
        key = t.strip().lower().replace("-", " ")
        for slot in _TIMING_ALIASES.get(key, [key] if key in _SLOT_ORDER else []):
            if slot not in slots:
                slots.append(slot)
    return sorted(slots, key=lambda s: _SLOT_ORDER.get(s, 9))


def _active_on(item: CarePlanItem, day: str) -> bool:
    start = normalize_date(item.start_date) or day
    one_day = item.kind in (ItemKind.TEST, ItemKind.APPOINTMENT, ItemKind.TREATMENT)
    end = normalize_date(item.end_date) or (start if one_day else "9999-12-31")
    if end < start:  # typo in the plan: show it on the start day only
        end = start
    return start <= day <= end


def build_checklist(items: list[CarePlanItem], day: str) -> list[ChecklistItem]:
    """Pure function: plan items → the day's tickable rows."""
    day = normalize_date(day) or day
    rows: dict[tuple, ChecklistItem] = {}
    # Oldest first, so a newer approval of the same medicine overwrites the older one.
    for it in sorted(items, key=lambda i: i.id or 0):
        if not _active_on(it, day):
            continue
        base = f"{it.name} {it.dose}".strip()
        if it.notes:
            base += f" ({it.notes})"
        kind = ItemKind(it.kind)
        if kind in (ItemKind.MEDICATION, ItemKind.INSTRUCTION):
            slots = normalize_timings(it.timings)
            if not slots:  # "as needed" items are not ticked daily
                continue
            for slot in slots:
                rows[(kind, it.name.strip().lower(), slot)] = ChecklistItem(it.id, f"{base} — {slot}", kind, slot)
        else:
            rows[(kind, it.name.strip().lower(), "")] = ChecklistItem(it.id, base, kind, "")
    return sorted(rows.values(), key=lambda r: (_SLOT_ORDER.get(r.slot, 9), r.label))


def get_today_checklist(patient_id: int, day: str | None = None) -> list[ChecklistItem]:
    day = day or date.today().isoformat()
    return build_checklist(db.list_plan_items(patient_id), day)