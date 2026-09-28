"""
Load the demo patient into SQLite + Hindsight.  Owner: Shreyan.

    python -m seed.load_seed            # load Rajesh (skips if already loaded)
    python -m seed.load_seed --dry-run  # print what would be stored, touch nothing remote

Every past daily log is saved exactly the way the Patient page saves it: a locked
DailyLog row in SQLite (so the doctor summary gets exact adherence counts) plus the
same checklist / symptom / diary / visit-note memories in Hindsight. Today is left
open so the live demo can fill it in.

Set HINDSIGHT_BANK_PREFIX=demo in .env before loading the FINAL demo bank.
While developing, keep your own prefix (dev-shreyan, dev-samprada, dev-niya).
To reload from scratch: delete data/onko.db AND switch to a fresh bank prefix
(bank ids are "<prefix>-patient-<id>", so the old bank would get duplicates).
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta

from core import db, memory, schedule
from core.contracts import CheckStatus, DailyLog, Entry, EntryType, Role
from seed import rajesh


def d(offset: int) -> str:
    """Day offset from today → ISO date."""
    return (date.today() + timedelta(days=offset)).isoformat()


def at(offset: int, hour: int) -> datetime:
    """Day offset + hour → datetime."""
    return datetime.combine(date.today() + timedelta(days=offset), datetime.min.time()).replace(hour=hour)


def build_day(patient_id: int, offset: int, spec: dict) -> tuple[DailyLog, list[Entry]]:
    """One past day → (locked DailyLog, memories formatted exactly like the Patient page)."""
    day = d(offset)
    ts = at(offset, 21)
    checklist = schedule.get_today_checklist(patient_id, day)
    for ci in checklist:
        ci.status = next((s for key, s in spec.get("status", {}).items() if key in ci.label), CheckStatus.DONE)

    mood, symptoms, note = spec.get("mood", ""), spec.get("symptoms", []), spec.get("note", "")
    log = DailyLog(patient_id, day, checklist, mood, symptoms, note,
                   spec.get("diary", ""), spec.get("visit_note", ""), ts)

    p, entries = Role.PATIENT, []
    if checklist:
        lines = "\n".join(f"- {c.label}: {c.status.value}" for c in checklist)
        entries.append(Entry(patient_id, f"Daily check-in for {day}:\n{lines}", p, EntryType.CHECKLIST, ts))
    if mood or symptoms or note:
        text = f"Mood: {mood or 'not given'}. Symptoms: {', '.join(symptoms) or 'none'}. {note}".strip()
        entries.append(Entry(patient_id, text, p, EntryType.SYMPTOM, ts))
    if log.diary:
        entries.append(Entry(patient_id, log.diary, p, EntryType.DIARY, ts))
    if log.visit_note:
        entries.append(Entry(patient_id, f"Patient's note after appointment: {log.visit_note}", p, EntryType.VISIT_NOTE, ts))
    return log, entries


def load_patient(seed_module, dry_run: bool = False) -> None:
    """Create the patient, plan, past daily logs and memories (chronological)."""
    p = seed_module.PATIENT
    existing = next((x for x in db.list_patients() if x.name == p["name"]), None)
    if existing and not dry_run:
        print(f"{p['name']} is already loaded as patient #{existing.id}. Nothing to do.\n"
              "To reload: delete data/onko.db and use a new HINDSIGHT_BANK_PREFIX.")
        return

    patient = db.create_patient(p["name"], p["age"], p["diagnosis"])
    db.add_plan_items(patient.id, seed_module.plan_items(d))
    bank = memory.ensure_bank(patient) if not dry_run else "(dry run, no bank)"

    entries = [Entry(patient.id, text, src, etype, at(off, hour)) for off, hour, src, etype, text in seed_module.ENTRIES]
    logs = 0
    for offset in range(seed_module.FIRST_DAY, 0):
        if offset in seed_module.NOT_LOGGED:
            continue
        log, day_entries = build_day(patient.id, offset, seed_module.DAYS.get(offset, {}))
        if not dry_run:
            db.save_daily_log(log)
        entries += day_entries
        logs += 1
    entries.sort(key=lambda e: e.timestamp)  # oldest first, like real life

    print(f"Patient #{patient.id} {patient.name} → bank '{bank}' "
          f"(Hindsight {'online' if memory.is_online() else 'OFFLINE'}) · {logs} daily logs · {len(entries)} memories")
    started = time.time()
    for i, e in enumerate(entries, 1):
        if dry_run:
            print(f"  {e.timestamp:%d %b %H:%M} {e.source.value:8} {e.type.value:12} {e.content.splitlines()[0][:70]}")
            continue
        memory.save_entry(e)
        print(f"  [{i}/{len(entries)}] {e.timestamp:%d %b} {e.type.value:12} ({time.time() - started:.0f}s)")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:  # throwaway database so data/onko.db is untouched
        db.config.DB_PATH = db.config.ROOT / "data" / "dry_run.db"
        db.config.DB_PATH.unlink(missing_ok=True)
    db.init_db()
    load_patient(rajesh, dry_run)
    if dry_run:
        db.config.DB_PATH.unlink(missing_ok=True)
        print("Dry run: nothing was saved.")
    else:
        print("Done. Hindsight builds observations in the background. Give it a few minutes before the demo.")


if __name__ == "__main__":
    main()
