"""
Checklist edge-case tests. Owner: Samprada.   Run:  python -m tests.test_schedule
No API keys or database needed.
"""

from core.contracts import CarePlanItem as P, ItemKind as K
from core.schedule import build_checklist, normalize_date, normalize_timings

DAY = "2026-09-27"
passed = 0


def check(name, got, want):
    global passed
    assert got == want, f"✗ {name}\n   got:  {got}\n   want: {want}"
    passed += 1
    print(f"✓ {name}")


def labels(items, day=DAY):
    return [r.label for r in build_checklist(items, day)]


# ── Dates ──
check("ISO date", normalize_date("2026-09-03"), "2026-09-03")
check("'3 Sep 2026'", normalize_date("3 Sep 2026"), "2026-09-03")
check("'03/09/2026' (Indian day/month)", normalize_date("03/09/2026"), "2026-09-03")
check("unpadded '2026-9-3'", normalize_date("2026-9-3"), "2026-09-03")
check("empty / junk → ''", (normalize_date(""), normalize_date("next week")), ("", ""))

# ── Timings ──
check("'Morning' → morning", normalize_timings(["Morning"]), ["morning"])
check("'twice daily' → morning + evening", normalize_timings(["twice daily"]), ["morning", "evening"])
check("'BD' → morning + evening", normalize_timings(["BD"]), ["morning", "evening"])
check("'bedtime' → night", normalize_timings(["bedtime"]), ["night"])
check("duplicates removed, day order", normalize_timings(["evening", "Morning", "morning"]), ["morning", "evening"])
check("unknown timing ignored", normalize_timings(["whenever"]), [])

# ── Medication date range ──
med = lambda s, e: [P(K.MEDICATION, "Capecitabine", "1500 mg", ["morning", "evening"], s, e, id=1)]
check("on start day", len(labels(med("2026-09-27", "2026-10-10"))), 2)
check("on end day", len(labels(med("2026-09-14", "2026-09-27"))), 2)
check("day after end → gone", labels(med("2026-09-01", "2026-09-26")), [])
check("before start → not yet", labels(med("2026-09-28", "2026-10-10")), [])
check("no end date → ongoing", len(labels(med("2026-01-01", ""))), 2)
check("messy dates still work", len(labels(med("20 Sep 2026", "03/10/2026"))), 2)
check("end before start (typo) → start day only", len(labels(med("2026-09-27", "2026-09-20"))), 2)

# ── As-needed ──
check("as-needed (no timings) not on checklist",
      labels([P(K.MEDICATION, "Ondansetron", "8 mg", [], "2026-09-24", "", id=2)]), [])

# ── One-day events ──
test = [P(K.TEST, "CBC", "", [], "2026-10-01", "", id=3)]
check("test only on its day", (labels(test), len(labels(test, "2026-10-01"))), ([], 1))
appt = [P(K.APPOINTMENT, "Review with Dr. Mehta", "", [], "2026-09-27", "", "bring CBC report", id=4)]
check("appointment shows with note", labels(appt), ["Review with Dr. Mehta (bring CBC report)"])

# ── Plan revised ──
revised = [
    P(K.MEDICATION, "Capecitabine", "1500 mg", ["morning", "evening"], "2026-09-24", "2026-10-07", id=1),
    P(K.MEDICATION, "capecitabine", "1000 mg", ["morning", "evening"], "2026-09-26", "2026-10-07", id=9),
]
check("newest approval wins, no duplicates",
      labels(revised), ["capecitabine 1000 mg — morning", "capecitabine 1000 mg — evening"])

# ── Ordering ──
mixed = [
    P(K.INSTRUCTION, "Drink 2 litres of water", "", ["daily"], "2026-09-24", "", id=5),
    P(K.MEDICATION, "Capecitabine", "1500 mg", ["evening", "morning"], "2026-09-24", "", id=1),
]
check("sorted morning → evening → daily", [r.slot for r in build_checklist(mixed, DAY)], ["morning", "evening", "daily"])

print(f"\nAll {passed} checks passed.")