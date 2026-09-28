"""
OnKo Memory — shared contracts.

⚠️  LOCKED FILE. Every module and every AI agent builds against these shapes.
    Do NOT change a field or function signature without announcing it in the
    team group chat. After a change, everyone pulls `main`.

This file holds:
  1. Enums (roles, entry types, item kinds, statuses)
  2. Dataclasses passed between the UI, core logic, AI and memory layers
  3. The PUBLIC API list — which functions each module must expose

Dates are ISO strings ("2026-09-27") and datetimes are Python `datetime`
objects, so everything is easy to store in SQLite and JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ─────────────────────────────── Enums ────────────────────────────────

class Role(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    NURSE = "nurse"


class EntryType(str, Enum):
    """What kind of information an Entry is. Stored as Hindsight context."""
    CARE_PLAN = "care_plan"      # doctor-approved plan items
    REPORT = "report"            # extracted report values (PDF)
    DOCTOR_NOTE = "doctor_note"  # free-text notes from doctor/nurse
    CHECKLIST = "checklist"      # patient's daily done/missed/late
    SYMPTOM = "symptom"          # mood + symptom chips + note
    DIARY = "diary"              # free-text "tell us anything"
    VISIT_NOTE = "visit_note"    # "what did the doctor tell you today?"
    CHAT = "chat"                # chatbot messages
    SOS = "sos"                  # danger-word / emergency events


class ItemKind(str, Enum):
    MEDICATION = "medication"
    TEST = "test"
    APPOINTMENT = "appointment"
    TREATMENT = "treatment"
    INSTRUCTION = "instruction"  # e.g. "drink 2L water daily"


class CheckStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    MISSED = "missed"
    LATE = "late"


# Fixed UI options (kept here so UI + seed data + AI all use the same words)
MOODS: list[str] = ["😊 Good", "😐 Okay", "😟 Not good"]
SYMPTOMS: list[str] = [
    "Nausea", "Tiredness", "Pain", "Fever",
    "No appetite", "Loose motions", "Sleep trouble",
]
TIME_SLOTS: list[str] = ["morning", "afternoon", "evening", "night", "daily"]


# ───────────────────────────── Dataclasses ─────────────────────────────

@dataclass
class Patient:
    id: int
    name: str
    age: int | None = None
    diagnosis: str = ""


@dataclass
class Entry:
    """One piece of information saved to a patient's Hindsight memory bank."""
    patient_id: int
    content: str                       # human-readable text of what happened
    source: Role                       # who provided it
    type: EntryType                    # what kind of information it is
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class CarePlanItem:
    """One item of the doctor-approved care plan.

    Medications/instructions use `timings` + start/end dates.
    Tests/appointments/treatments use `start_date` as the event date.
    """
    kind: ItemKind
    name: str                          # "Capecitabine", "CBC", "Review visit"
    dose: str = ""                     # "1500 mg"
    timings: list[str] = field(default_factory=list)  # values from TIME_SLOTS
    start_date: str = ""               # ISO date
    end_date: str = ""                 # ISO date ("" = same as start / ongoing)
    notes: str = ""                    # "after food", "fasting", ...
    id: int | None = None              # set by the database


@dataclass
class ChecklistItem:
    """One tickable row in the patient's daily check-in."""
    plan_item_id: int | None
    label: str                         # "Capecitabine 1500 mg — morning"
    kind: ItemKind
    slot: str = ""                     # "morning", "evening", ...
    status: CheckStatus = CheckStatus.PENDING


@dataclass
class DailyLog:
    """Everything the patient submits for one day (then the form locks)."""
    patient_id: int
    day: str                           # ISO date
    checklist: list[ChecklistItem] = field(default_factory=list)
    mood: str = ""
    symptoms: list[str] = field(default_factory=list)
    symptom_note: str = ""
    diary: str = ""
    visit_note: str = ""
    submitted_at: datetime | None = None


@dataclass
class ReportValue:
    name: str                          # "Hb"
    value: str                         # "9.2"
    unit: str = ""                     # "g/dL"


@dataclass
class ExtractedReport:
    report_name: str                   # "CBC"
    report_date: str                   # ISO date, "" if unknown
    values: list[ReportValue] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class ChatReply:
    text: str
    is_emergency: bool = False         # danger words detected → urgent reply
    flagged_for_doctor: bool = False   # needs doctor attention


# ─────────────────────────────── PUBLIC API ───────────────────────────────
# Each owner implements these in their module. Signatures must not change.
#
# core/db.py            (Samprada)
#   init_db() -> None
#   create_patient(name: str, age: int | None, diagnosis: str) -> Patient
#   list_patients() -> list[Patient]
#   get_patient(patient_id: int) -> Patient | None
#   add_plan_items(patient_id: int, items: list[CarePlanItem]) -> list[CarePlanItem]
#   list_plan_items(patient_id: int) -> list[CarePlanItem]
#   save_daily_log(log: DailyLog) -> None
#   get_daily_log(patient_id: int, day: str) -> DailyLog | None
#   mark_reviewed(patient_id: int, when: datetime | None = None) -> None
#   last_reviewed(patient_id: int) -> datetime | None
#
# core/memory.py        (Samprada)
#   is_online() -> bool
#   ensure_bank(patient: Patient) -> str
#   save_entry(entry: Entry) -> None
#   ask(patient_id: int, question: str, context: str = "") -> str
#   recent_saves(patient_id: int, limit: int = 5) -> list[dict]      # {type, source, when, text}
#   last_trace(patient_id: int) -> dict | None                        # {question, facts, directives, seconds, offline}
#   learned_patterns(patient_id: int, limit: int = 6) -> list[str]    # Hindsight observations
#
# core/schedule.py      (Samprada)
#   build_checklist(items: list[CarePlanItem], day: str) -> list[ChecklistItem]
#   get_today_checklist(patient_id: int, day: str | None = None) -> list[ChecklistItem]
#
# core/chat.py          (Samprada)
#   handle_message(patient_id: int, text: str, role: Role = Role.PATIENT) -> ChatReply
#   since_last_visit(patient_id: int) -> str
#
# core/ai/extract.py    (Shreyan)
#   extract_care_plan(text: str, today: str) -> list[CarePlanItem]
#
# core/ai/pdf.py        (Shreyan)
#   read_pdf_text(file_bytes: bytes) -> str
#   extract_report(text: str) -> ExtractedReport
#
# app/                  (Niya) — Streamlit pages only call the functions above.
