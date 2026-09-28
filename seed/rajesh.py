"""
Demo patient: Rajesh Kumar, 58, stage III colon cancer on adjuvant CAPOX. Owner: Shreyan.

Offsets are days from the day you run the loader (0 = today), so the demo always
looks current. 21-day CAPOX cycles, oxaliplatin infusion on day 1, capecitabine on days 1–14:

    Cycle 2  infusion day -45   capecitabine -45 … -32   rest -31 … -25
    Cycle 3  infusion day -24   capecitabine -24 … -11   rest -10 … -4
    Cycle 4  infusion day  -3   capecitabine  -3 … +10   ← today is day 4 of cycle 4
    Next: CBC + LFT day +4, review day +11, Cycle 5 day +18

Patterns hidden in the data for Hindsight to discover (nobody states them outright):
  • Nausea + poor appetite 1–2 days after EVERY infusion (3 cycles in a row)
  • Missed/late doses are always the EVENING capecitabine (travel, tiredness, functions)
  • Cold-triggered tingling that started in cycle 2 and keeps coming back
  • Red, sore palms in week 2 of cycle 3; settled with moisturiser
  • Worry and poor sleep the day or two before each new cycle
  • Daughter Priya handles report uploads and appointments
"""

from core.contracts import CarePlanItem, CheckStatus, EntryType, ItemKind, Role

PATIENT = {"name": "Rajesh Kumar", "age": 58, "diagnosis": "Colon cancer (stage III), adjuvant CAPOX"}

INFUSION_DAYS = (-45, -24, -3)   # cycles 2, 3, 4
FIRST_DAY = -45                  # first day with a daily log
CAPE = "Capecitabine"
CAPE_NOTES = "after food, days 1–14"


def plan_items(d) -> list[CarePlanItem]:
    """Every approved plan item across the three cycles. `d(offset)` → ISO date."""
    items: list[CarePlanItem] = [
        CarePlanItem(ItemKind.INSTRUCTION, "Drink 2 litres of water", "", ["daily"], d(FIRST_DAY), "", ""),
        CarePlanItem(ItemKind.MEDICATION, "Ondansetron", "8 mg", [], d(FIRST_DAY), "", "only if nausea, before meals"),
    ]
    for cycle, day1 in zip((2, 3, 4), INFUSION_DAYS):
        items += [
            CarePlanItem(ItemKind.TREATMENT, f"CAPOX Cycle {cycle}: Oxaliplatin infusion", "", [], d(day1), "", "day-care, 10 AM"),
            CarePlanItem(ItemKind.MEDICATION, CAPE, "1500 mg", ["morning", "evening"], d(day1), d(day1 + 13), CAPE_NOTES),
        ]
    items += [
        CarePlanItem(ItemKind.TEST, "CBC + LFT blood test", "", [], d(4), "", "hospital lab, 9 AM, fasting not needed"),
        CarePlanItem(ItemKind.APPOINTMENT, "Review with Dr. Mehta", "", [], d(11), "", "bring the CBC report"),
        CarePlanItem(ItemKind.TREATMENT, "CAPOX Cycle 5: Oxaliplatin infusion", "", [], d(18), "", "day-care, 10 AM"),
    ]
    return items


# ─────────────── Daily logs ───────────────
# Default for a logged day: every checklist item done, no mood/symptom entry
# (on good days the patient just ticks the checklist). Only exceptions are listed.
#
#   offset: {"status": {checklist-label substring: CheckStatus},
#            "mood": str, "symptoms": [..], "note": str, "diary": str, "visit_note": str}

M, E, W = "— morning", "— evening", "Drink 2 litres"   # checklist label substrings
GOOD, OK, BAD = "😊 Good", "😐 Okay", "😟 Not good"

NOT_LOGGED = {-38, -29, -19, -8}   # travel / forgot / unwell: real patients skip days

DAYS: dict[int, dict] = {
    # ── Cycle 2 ──
    -45: {"mood": OK, "symptoms": ["Tiredness"], "note": "Tired after the infusion, slept in the afternoon."},
    -44: {"mood": BAD, "symptoms": ["Nausea", "No appetite"], "note": "Nausea started after breakfast. Took Ondansetron once."},
    -43: {"mood": OK, "symptoms": ["Nausea", "Tiredness"], "note": "Still queasy in the morning, better by evening."},
    -42: {"mood": OK, "symptoms": ["Tiredness"]},
    -41: {"diary": "Fingers tingled when I held a cold glass of water from the fridge."},
    -39: {"status": {E: CheckStatus.LATE},
          "diary": "Went to Warangal for my nephew's engagement. Took the evening tablet at 11 pm after dinner."},
    -35: {"mood": GOOD, "diary": "Walked 20 minutes in the colony park in the morning."},
    -33: {"status": {W: CheckStatus.MISSED}, "mood": OK, "symptoms": ["Loose motions"], "note": "Loose motions twice today."},
    -30: {"mood": GOOD, "diary": "Last few days have been good. Appetite is back to normal."},
    -26: {"mood": OK, "symptoms": ["Sleep trouble"], "note": "Could not sleep well, worried about the next cycle."},
    # ── Cycle 3 ──
    -24: {"mood": OK, "symptoms": ["Tiredness"], "note": "Infusion day. Hands felt cold and tingly during the drip."},
    -23: {"mood": BAD, "symptoms": ["Nausea", "No appetite"], "note": "Nausea again after breakfast, same as last cycle."},
    -22: {"mood": OK, "symptoms": ["Nausea", "Tiredness"],
          "diary": "Cold water feels like needles in my throat. Drinking warm water instead."},
    -21: {"status": {E: CheckStatus.MISSED}, "mood": OK, "symptoms": ["Tiredness"],
          "diary": "Felt very tired and slept early, forgot the evening tablet."},
    -17: {"mood": OK, "symptoms": ["Pain"], "note": "Palms look red and feel sore when I hold the scooter handle."},
    -15: {"mood": OK, "symptoms": ["Pain"], "note": "Palms still sore. Using the moisturiser the nurse suggested."},
    -14: {"status": {E: CheckStatus.LATE},
          "diary": "Family function in the evening. Took the tablet after coming home at 10:30 pm."},
    -12: {"mood": GOOD, "diary": "Palms are much better now."},
    -9:  {"status": {W: CheckStatus.MISSED}, "diary": "Forgot to keep the water bottle with me at the bank."},
    -6:  {"mood": GOOD, "diary": "Walked 30 minutes today. Priya booked my next blood test."},
    -5:  {"mood": OK, "symptoms": ["Sleep trouble"], "note": "Worried about the next cycle again, slept late."},
    # ── Cycle 4 ──
    -3:  {"mood": OK, "symptoms": ["Tiredness"],
          "visit_note": "Doctor said eat smaller meals, avoid cold things, and come back if fever goes above 100."},
    -2:  {"mood": BAD, "symptoms": ["Nausea", "Tiredness"], "note": "Nausea again after breakfast, same as the last two cycles."},
    -1:  {"status": {E: CheckStatus.LATE, W: CheckStatus.MISSED}, "mood": OK, "symptoms": ["Nausea", "No appetite"],
          "note": "Took Ondansetron twice. Evening tablet late because I could not eat dinner on time."},
}


# ─────────────── Other memories (care team, reports, chat) ───────────────
# (day_offset, hour, source, type, content)
ENTRIES = [
    # Cycle 2
    (-46, 12, Role.DOCTOR, EntryType.REPORT,
     "CBC before cycle 2: Hb 11.2 g/dL, WBC 5.6 x10^9/L, Platelets 214 x10^9/L, ANC 3.4 x10^9/L. "
     "LFT: Bilirubin 0.7 mg/dL, ALT 28 U/L, AST 31 U/L."),
    (-45, 10, Role.DOCTOR, EntryType.CARE_PLAN,
     "Cycle 2 of CAPOX started today with oxaliplatin infusion. Capecitabine 1500 mg twice daily after food, "
     "days 1–14. Ondansetron 8 mg before meals only if nausea. Drink 2 litres of water daily."),
    (-45, 16, Role.NURSE, EntryType.DOCTOR_NOTE,
     "Infusion completed without issues. Daughter Priya accompanied the patient; she will handle report "
     "uploads and appointment bookings."),
    (-36, 11, Role.PATIENT, EntryType.CHAT, "patient said: Can I eat mangoes while on this medicine?"),
    (-25, 13, Role.PATIENT, EntryType.REPORT,
     "CBC before cycle 3 (uploaded by daughter Priya): Hb 10.1 g/dL, WBC 4.8 x10^9/L, Platelets 182 x10^9/L, "
     "ANC 2.6 x10^9/L."),
    # Cycle 3
    (-24, 10, Role.DOCTOR, EntryType.CARE_PLAN,
     "Cycle 3 of CAPOX started with oxaliplatin infusion. Same capecitabine dose, 1500 mg twice daily after "
     "food, days 1–14. Continue Ondansetron if nausea."),
    (-24, 11, Role.DOCTOR, EntryType.DOCTOR_NOTE,
     "Patient reports tingling in fingers with cold since cycle 2. Advised to avoid cold drinks and cold objects."),
    (-16, 12, Role.PATIENT, EntryType.CHAT, "patient said: Is it okay to put coconut oil on my red palms?"),
    (-16, 15, Role.NURSE, EntryType.DOCTOR_NOTE,
     "Phone call: patient has red, sore palms since day 8 of cycle 3. Advised moisturiser twice daily and "
     "avoiding hot water. Dr. Mehta informed."),
    (-10, 18, Role.PATIENT, EntryType.CHAT, "patient said: Can I travel to Vijayawada next month for a wedding?"),
    (-4, 13, Role.DOCTOR, EntryType.REPORT,
     "CBC before cycle 4: Hb 9.2 g/dL, WBC 4.1 x10^9/L, Platelets 156 x10^9/L, ANC 2.1 x10^9/L. "
     "LFT: Bilirubin 0.8 mg/dL, ALT 34 U/L, AST 36 U/L."),
    # Cycle 4
    (-3, 10, Role.DOCTOR, EntryType.CARE_PLAN,
     "Cycle 4 of CAPOX started with oxaliplatin infusion. Capecitabine 1500 mg twice daily after food, "
     "days 1–14. CBC + LFT in one week. Review with Dr. Mehta in two weeks. Cycle 5 in three weeks."),
    (-3, 12, Role.DOCTOR, EntryType.DOCTOR_NOTE,
     "Cold-triggered tingling continues, now also in the throat with cold water. Palms recovered. "
     "Patient prefers short, simple explanations; family speaks Telugu at home."),
]
