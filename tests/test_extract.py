"""
Care-plan extraction tests. Owner: Shreyan.   Run:  python -m tests.test_extract
No API keys needed: the Groq call is replaced by canned model outputs.
"""

from core.ai import extract, llm
from core.contracts import ItemKind as K

TODAY = "2026-09-28"
passed = 0


def check(name, got, want):
    global passed
    assert got == want, f"✗ {name}\n   got:  {got}\n   want: {want}"
    passed += 1
    print(f"✓ {name}")


# ── kinds & timings ──
check("kind synonyms", [extract.to_kind(k) for k in ["Medicine", "lab", "Follow-up", "chemo", "???"]],
      [K.MEDICATION, K.TEST, K.APPOINTMENT, K.TREATMENT, K.INSTRUCTION])
check("BD → morning+evening", extract.to_timings(["BD"]), ["morning", "evening"])
check("TDS → morning/afternoon/night", extract.to_timings("tds"), ["morning", "afternoon", "night"])
check("string with commas, day order", extract.to_timings("Night, Morning"), ["morning", "night"])
check("SOS / PRN → no slots", extract.to_timings(["SOS", "prn"]), [])
check("unknown words dropped", extract.to_timings(["whenever"]), [])

# ── dates ──
check("ISO kept", extract.to_iso_date("2026-10-03", TODAY), "2026-10-03")
check("'3 Oct 2026'", extract.to_iso_date("3 Oct 2026", TODAY), "2026-10-03")
check("'03/10/2026' is day/month", extract.to_iso_date("03/10/2026", TODAY), "2026-10-03")
check("'3rd October' no year → this year", extract.to_iso_date("3rd October", TODAY), "2026-10-03")
check("'5 Jan' no year, already passed → next year", extract.to_iso_date("5 Jan", TODAY), "2027-01-05")
check("garbage → ''", extract.to_iso_date("soon", TODAY), "")

# ── clean_items ──
DOCTOR_TEXT = ("Capecitabine 1500mg BD after food days 1-14. Ondansetron 8mg SOS for nausea. "
               "CBC on 3 Oct. Review with Dr Mehta 10/10/2026. Drink 2L water daily.")
raw = [
    {"kind": "medicine", "name": "Capecitabine", "dose": "1500 mg", "timings": "twice daily",
     "start_date": "2026-10-11", "end_date": "2026-09-28", "notes": "after food"},          # reversed range
    {"kind": "medication", "name": "Ondansetron", "dose": "8 mg", "timings": ["SOS"], "notes": "if nausea"},
    {"kind": "lab", "name": "CBC", "timings": ["morning"], "start_date": "3 Oct 2026", "end_date": "4 Oct 2026"},
    {"kind": "follow-up", "name": "Review with Dr Mehta", "start_date": "10/10/2026"},
    {"kind": "advice", "name": "Drink 2L water", "timings": ["daily"]},
    {"kind": "medication", "name": "Capecitabine", "dose": "1500 mg", "timings": ["morning", "evening"],
     "start_date": "2026-09-28", "end_date": "2026-10-11", "notes": "after food"},          # duplicate
    {"kind": "medication", "name": "Dexamethasone", "dose": "4 mg", "timings": ["morning"]},  # invented
    {"kind": "test", "name": "   "},                                                         # empty
    "not a dict",
]
items = extract.clean_items(raw, TODAY, DOCTOR_TEXT)
names = [i.name for i in items]
cap = items[0]

check("empty/non-dict rows dropped, duplicate merged", names,
      ["Capecitabine", "Ondansetron", "CBC", "Review with Dr Mehta", "Drink 2L water", "Dexamethasone"])
check("reversed date range fixed", (cap.start_date, cap.end_date), ("2026-09-28", "2026-10-11"))
check("'twice daily' string → slots", cap.timings, ["morning", "evening"])
check("PRN medicine has no slots, starts today", (items[1].timings, items[1].start_date), ([], TODAY))
check("test: no slots, single day, ISO date", (items[2].kind, items[2].timings, items[2].start_date, items[2].end_date),
      (K.TEST, [], "2026-10-03", ""))
check("appointment day/month date", (items[3].kind, items[3].start_date), (K.APPOINTMENT, "2026-10-10"))
check("instruction defaults to today", (items[4].kind, items[4].start_date), (K.INSTRUCTION, TODAY))
check("invented medicine flagged for the doctor", extract.UNVERIFIED_NOTE in items[5].notes, True)
check("real medicines not flagged", any(extract.UNVERIFIED_NOTE in i.notes for i in items[:5]), False)

# ── JSON parsing & retries ──
check("fenced JSON", llm.parse_json_object('```json\n{"items": []}\n```'), {"items": []})
check("prose around JSON", llm.parse_json_object('Sure! {"items": [1]} Hope this helps'), {"items": [1]})
check("bare list wrapped", llm.parse_json_object('[{"name": "CBC"}]'), {"items": [{"name": "CBC"}]})

replies = iter(["I cannot comply", '{"items": [{"kind": "test", "name": "CBC", "start_date": "2026-10-03"}]}'])
llm._complete = lambda system, user, json_mode: next(replies)
llm.time.sleep = lambda s: None
check("retry after unreadable reply", llm.chat_json("s", "u")["items"][0]["name"], "CBC")

calls = []
def _json_mode_fails(system, user, json_mode):
    calls.append(json_mode)
    if json_mode:
        raise Exception("Error code: 400 - json_validate_failed")
    return '{"items": []}'
llm._complete = _json_mode_fails
check("Groq json_validate_failed → retried without JSON mode", (llm.chat_json("s", "u"), calls), ({"items": []}, [True, False]))

llm._complete = lambda system, user, json_mode: "nope"
try:
    llm.chat_json("s", "u")
    check("gives up after 3 tries", "no error", "RuntimeError")
except RuntimeError:
    check("gives up after 3 tries", True, True)

# ── end to end with a fake model ──
extract.chat_json = lambda system, user: {"items": raw[:2]}
got = extract.extract_care_plan(DOCTOR_TEXT, TODAY)
check("extract_care_plan end to end", [(i.name, i.timings) for i in got],
      [("Capecitabine", ["morning", "evening"]), ("Ondansetron", [])])
check("blank text → no call, no items", extract.extract_care_plan("   ", TODAY), [])

print(f"\nAll {passed} checks passed.")
