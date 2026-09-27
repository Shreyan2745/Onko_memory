OnKo Memory 🩺

A cancer-care companion that remembers the whole journey.
The doctor enters the care plan, the patient logs their day, and a chatbot remembers
everything — getting more personal every week — built on Hindsight memory.

The doctor decides the care. OnKo remembers the journey.

Team Chai++ — Samprada Reddy · Niya Singh Shekhawat · Shreyan Samal ·

---

The problem

Cancer treatment runs for months. Patients juggle chemo cycles, tablets, blood tests, and
side effects, and forget what was said at the last visit. Doctors see the patient for a few
minutes every few weeks and miss what happened in between.

What OnKo does

Column 1	Column 2	Column 3
Dashboard	Who	What
Care team	Doctor / Nurse	Types the care plan in plain text → AI structures it → doctor approves. Uploads PDF reports (values extracted, then confirmed). Adds notes. Gets a “Since last visit” summary.
Patient	Patient	Once a day: checklist (✅ done / ❌ missed / ⏰ late), mood + symptoms, diary, after-appointment note → locks for the day. Below: a chatbot that answers from their full history.


How Hindsight memory is used

* One memory bank per patient. Everything from the doctor, nurse, and patient is stored with retain(), tagged with who recorded it, what type it is, and when.
* reflect() powers the chatbot and the doctor summary, answering from the patient’s memory with sources.
* Observations = learning. Hindsight automatically consolidates facts into patterns nobody typed — e.g., “nausea on days 2–3 after each oxaliplatin infusion” — so answers get more personal over time.
* Directives = safety. Hard rules on every bank: cite sources, never interpret lab values, never change medicines, never diagnose. See core/memory.py.
* Temporal recall handles “what did the doctor say last week?”

Architecture

Streamlit (app/) ──► core/ ──► Hindsight  (memory: 1 bank per patient)
                       ├────► SQLite     (patients, care-plan schedule, daily-log lock)
                       └────► Groq       (care-plan + report extraction)

Run it

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # add Hindsight + Groq keys
python -m scriptscheck_setup         # verify connections
python -m seedload_seed              # load demo patient Rajesh Kumar (4 weeks of history)
streamlit run app/Home.py

No keys yet? Set ONKO_STUBS=1 — the UI works with sample data and an offline memory fallback.

Repo structure

app/            Streamlit UI (Home, Doctor, Patient)
core/
  contracts.py  shared data shapes + public API (locked)
  memory.py     Hindsight: banks, directives, retain, reflect
  db.py         SQLite
  schedule.py   care plan → daily checklist
  chat.py       chatbot + "since last visit"
  ai/           Groq extraction (care plan, PDF reports)
seed/           demo patient data + loader
scripts/        setup check

Safety

OnKo organizes, summarizes, and structures. It never diagnoses, interprets lab values,
predicts risk, or recommends treatment changes. Danger words trigger an immediate
“contact your doctor / call 108” reply and an SOS entry for the care team.
Prototype for a hackathon — not a medical device.

---

Team workflow (delete before final submission)

* Branches: shreyan/ai, samprada/core, niya/ui. Commit hourly.
* Merge to main one branch at a time at sync points; run the app after each merge.
* git pull at the start of every new AI session. Never force-push.
* Test on your own bank prefix (dev-<name>). Only seed.load_seed with prefix demo touches the demo bank.
* Ownership + AI rules: see AGENTS.md.


