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


# Word-form variants the plain term list misses ("vomited blood", "coughed up blood", ...)
DANGER_PATTERNS = [
    r"\b(vomit\w*|threw up|throwing up|throw up|puk\w*)\b.{0,25}\bblood",
    r"\bblood\b.{0,15}\b(vomit\w*|puk\w*)",
    r"\bcough\w*\b.{0,15}\bblood",
    r"\bblood\b.{0,10}\b(in|with)\b.{0,10}\b(stool|motion|poop|urine)",
    r"\b(can'?t|cannot|won'?t) stop bleeding",
    r"\b(short of breath|hard to breathe|difficulty breathing|trouble breathing|passed out|having (a )?fits?)\b",
]


# Questions about taking / missing medicines get exact counts from the daily logs.
ADHERENCE_QUESTION = re.compile(
    r"\b(miss\w*|forg[eo]t\w*|skip\w*|late|on time|adherence|took|taken|taking)\b", re.I)


def _is_danger(text: str) -> bool:
    t = text.lower()
    if any(term in t for term in DANGER_TERMS):
        return True
    if any(re.search(p, t) for p in DANGER_PATTERNS):
        return True
    # Heart rate: "140 bpm", "heart rate 140", "pulse is 130"
    for m in re.finditer(r"(?:heart ?rate|pulse|hr)\D{0,15}(\d{2,3})|(\d{2,3})\s*bpm", t):
        bpm = int(m.group(1) or m.group(2))
        if bpm >= 120 or bpm <= 45:
            return True
    # Fever: "fever 101", "temp 38.5", and number-first "101 fever", "38.5 degree temperature"
    fever_after = r"(?:fever|temp(?:erature)?)\D{0,15}(\d{2,3}(?:\.\d)?)"
    fever_before = r"(\d{2,3}(?:\.\d)?)\s*(?:°|deg\w*)?\s*(?:f|c)?\b[^.\d]{0,12}\b(?:fever|temp(?:erature)?)"
    for m in [*re.finditer(fever_after, t), *re.finditer(fever_before, t)]:
        v = float(m.group(1))
        if v >= 100.4 or 38.0 <= v < 45:
            return True
    return False


def handle_message(patient_id: int, text: str, role: Role = Role.PATIENT) -> ChatReply:
    memory.save_entry(Entry(patient_id, f"{role.value} said: {text}", role, EntryType.CHAT))

    if _is_danger(text):
        memory.save_entry(Entry(patient_id, f"SOS / danger words in message: {text}", role, EntryType.SOS))
        return ChatReply(EMERGENCY_REPLY, is_emergency=True, flagged_for_doctor=True)

    context = PATIENT_CONTEXT
    if ADHERENCE_QUESTION.search(text):
        # Exact missed AND late counts from the daily logs, so the answer doesn't undercount.
        counts = db.adherence_text(patient_id, datetime.now() - timedelta(days=60))
        if counts:
            context += ("\nVerified medicine check-ins from the app's daily logs (use these exact "
                        "numbers; mention both missed and late doses with their dates):\n" + counts)
    answer = memory.ask(patient_id, text, context=context)
    # OnKo's own reply is NOT saved to memory: saved replies were later cited as if they
    # were clinical records ("as noted by the assistant"). The patient's question is saved above.
    return ChatReply(answer)


def since_last_visit(patient_id: int) -> str:
    """Doctor-facing factual summary of everything recorded since the last review."""
    since = db.last_reviewed(patient_id) or (datetime.now() - timedelta(days=30))
    counts = db.adherence_text(patient_id, since)
    if counts:
        # Exact numbers from the app's daily logs: the AI must not recount.
        adherence_rule = (
            "for the days listed below, use EXACTLY these verified counts from the app's "
            "daily logs; do not recount or change them. For any other days, count missed and "
            "late doses from the check-ins recorded in memory and add them, keeping each date. "
            "Then note whether misses cluster (e.g. evening doses) and include missed checklist "
            "items like water intake.\n" + counts
        )
    else:
        adherence_rule = (
            "count missed and late doses per medicine, note whether they cluster "
            "(e.g. evening doses, specific days), and include missed checklist items like water intake."
        )
    question = (
        f"Write a clinical handover summary of everything recorded for this patient "
        f"from {since:%d %b %Y} to today. The reader is the treating doctor. "
        "Refer to the patient in the third person ('the patient'), never 'you'.\n\n"
        "Use exactly these headings:\n"
        f"1. Medication adherence: {adherence_rule}\n"
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