"""
Patient chatbot + doctor "since last visit" summary. Owner: Samprada.

Flow for every patient message:
  1. Save the message to memory (so it becomes history too)
  2. Danger check (words + heart rate/fever numbers) → urgent reply + SOS entry (no LLM)
  3. Otherwise → memory.ask() (Hindsight reflect with directives)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from core import db, memory
from core.contracts import ChatReply, Entry, EntryType, Role

DANGER_TERMS = [
    "can't breathe", "cannot breathe", "breathing difficulty", "chest pain",
    "unconscious", "fainted", "seizure", "vomiting blood", "blood in vomit",
    "black stool", "heavy bleeding", "severe bleeding", "suicide", "sos",
]

EMERGENCY_REPLY = (
    "🚨 This sounds urgent. Please contact your doctor or go to the nearest "
    "emergency department right now. If you can't get there, call 108 (ambulance). "
    "I've flagged this for your care team."
)

PATIENT_CONTEXT = (
    "The person asking is the patient, who prefers short, simple explanations. "
    "Reply in under 100 words, as 2-4 short sentences or a few short bullets. No headings.\n"
    "Answer from what is recorded in memory and say who recorded each fact and when.\n"
    "If they ask why they feel a symptom: do not diagnose, but do point out when it was "
    "reported relative to treatment dates, e.g. 'You logged nausea 1-2 days after your "
    "infusions on 3 Sep and 24 Sep.' Then suggest mentioning it to the care team.\n"
    "For routine medicine questions, be calm: suggest checking with the care team, "
    "not 'immediately', unless it sounds like an emergency."
)


def _is_danger(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in DANGER_TERMS):
        return True
    # Heart rate: "140 bpm", "heart rate 140", "pulse is 130"
    for m in re.finditer(r"(?:heart ?rate|pulse|hr)\D{0,15}(\d{2,3})|(\d{2,3})\s*bpm", t):
        bpm = int(m.group(1) or m.group(2))
        if bpm >= 120 or bpm <= 45:
            return True
    # Fever: "fever 101", "temp 38.5"
    for m in re.finditer(r"(?:fever|temp(?:erature)?)\D{0,15}(\d{2,3}(?:\.\d)?)", t):
        v = float(m.group(1))
        if v >= 100.4 or 38.0 <= v < 45:
            return True
    return False


def handle_message(patient_id: int, text: str, role: Role = Role.PATIENT) -> ChatReply:
    memory.save_entry(Entry(patient_id, f"{role.value} said: {text}", role, EntryType.CHAT))

    if _is_danger(text):
        memory.save_entry(Entry(patient_id, f"SOS / danger words in message: {text}", role, EntryType.SOS))
        return ChatReply(EMERGENCY_REPLY, is_emergency=True, flagged_for_doctor=True)

    answer = memory.ask(patient_id, text, context=PATIENT_CONTEXT)
    memory.save_entry(Entry(patient_id, f"OnKo answered: {answer}", role, EntryType.CHAT, metadata={"speaker": "assistant"}))
    return ChatReply(answer)


def since_last_visit(patient_id: int) -> str:
    """Doctor-facing factual summary of everything recorded since the last review."""
    since = db.last_reviewed(patient_id) or (datetime.now() - timedelta(days=30))
    question = (
        f"Write a clinical handover summary of everything recorded for this patient "
        f"from {since:%d %b %Y} to today. The reader is the treating doctor. "
        "Refer to the patient in the third person ('the patient'), never 'you'.\n\n"
        "Use exactly these headings:\n"
        "1. Medication adherence: count missed and late doses per medicine, note whether "
        "they cluster (e.g. evening doses, specific days), and include missed checklist items like water intake.\n"
        "2. Symptoms: each symptom with the dates reported. Then, for each repeating symptom, "
        "list every chemotherapy infusion or cycle-start date and state how many days after it "
        "the symptom was reported (e.g. 'nausea 1-2 days after both infusions: 3 Sep, 24 Sep'). "
        "Prefer this treatment-linked pattern over time-of-day patterns.\n"
        "3. Lab and scan reports: recorded values with dates only. No interpretation.\n"
        "4. Patient diary and care-team notes: brief points with who recorded them and when.\n"
        "5. Patient questions and SOS events: with dates.\n\n"
        "Only use information recorded in memory. If a section has nothing, write 'None recorded'. "
        "Do not interpret, diagnose or recommend."
    )
    return memory.ask(
        patient_id,
        question,
        context="The person asking is the treating doctor preparing for a consultation. "
                "Write for a clinician, in the third person.",
    )