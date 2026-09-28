"""Patient workspace — Stitch-matched frontend. Owner: Niya."""
from datetime import date, datetime
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import streamlit as st
from ui_common import app_footer, app_header, require_role, setup_page
from core import chat, db, memory, schedule
from core.contracts import MOODS, SYMPTOMS, CheckStatus, DailyLog, Entry, EntryType, ItemKind, Role

setup_page("Patient Workspace")
role, patient = require_role(Role.PATIENT)
today = date.today().isoformat()
app_header("Patient Workspace", patient)

# Days of care history = since the earliest approved care-plan item (0 if no plan yet).
def _days_remembered(patient_id: int) -> int:
    """Days since the earliest approved care-plan item started (0 if no plan yet)."""
    starts = []
    for item in db.list_plan_items(patient_id):
        try:
            starts.append(date.fromisoformat(item.start_date))
        except (TypeError, ValueError):
            continue  # blank or non-ISO date typed by hand
    return max((date.today() - min(starts)).days, 0) + 1 if starts else 0


days_remembered = _days_remembered(patient.id)
memory_badge = f"◌ {days_remembered} days remembered" if days_remembered else "◌ New patient"
_hour = datetime.now().hour
greeting = "Good morning" if _hour < 12 else "Good afternoon" if _hour < 17 else "Good evening"

st.markdown(
    f'<div class="hero-title">{greeting}, {patient.name.split()[0]} '
    f'<span class="badge">{memory_badge}</span></div>'
    f'<div class="hero-sub">Let\'s check in for today · {date.today():%A, %d %B}</div>',
    unsafe_allow_html=True,
)

STATUS_LABELS = {
    CheckStatus.DONE: "✓ Done",
    CheckStatus.MISSED: "✕ Missed",
    CheckStatus.LATE: "◷ Late",
}

care_col, chat_col = st.columns([1.55, 1], gap="large")

with care_col:
    with st.container(border=True):
        st.markdown('<div class="section-title">♢ Today\'s Care</div><div class="section-sub">Based on your approved care plan</div>', unsafe_allow_html=True)
        existing = db.get_daily_log(patient.id, today)

        if existing:
            st.success("✓ Today's log is complete")
            st.caption(f"Saved at {existing.submitted_at:%I:%M %p}" if existing.submitted_at else "Saved today")
            for ci in existing.checklist:
                st.markdown(f"**{ci.label}** &nbsp; <span class='badge'>{STATUS_LABELS.get(ci.status, ci.status.value)}</span>", unsafe_allow_html=True)
            st.markdown("---")
            st.markdown(f"**Mood** &nbsp; {existing.mood or '—'}")
            st.markdown(f"**Symptoms** &nbsp; {', '.join(existing.symptoms) or 'None reported'}")
            if existing.diary:
                st.markdown('<div class="memory-note">✦ <b>Added to care memory</b><br>' + existing.diary + '</div>', unsafe_allow_html=True)
        else:
            checklist = schedule.get_today_checklist(patient.id, today)
            has_appointment = any(c.kind in (ItemKind.APPOINTMENT, ItemKind.TREATMENT) for c in checklist)
            with st.form("daily_log"):
                st.markdown('<span class="badge">TODAY\'S SCHEDULE</span>', unsafe_allow_html=True)
                if not checklist:
                    st.caption("Nothing scheduled for today.")
                for i, ci in enumerate(checklist):
                    st.markdown(f"**{ci.label}**")
                    ci.status = st.radio(
                        f"Status {i}", list(STATUS_LABELS), format_func=STATUS_LABELS.get,
                        horizontal=True, index=None, key=f"ci_{i}", label_visibility="collapsed",
                    ) or CheckStatus.PENDING

                st.markdown('<div class="section-title" style="margin-top:1rem">☺ How are you feeling today?</div><div class="section-sub">Daily Reflection</div>', unsafe_allow_html=True)
                mood = st.radio("Mood", MOODS, horizontal=True, index=None, key="mood_selector", label_visibility="collapsed")
                symptoms = st.pills("Anything you're experiencing?", SYMPTOMS, selection_mode="multi") or []
                symptom_note = st.text_input("Add a little more detail", placeholder="e.g. Nausea started after lunch")

                st.markdown('<div class="section-title" style="margin-top:1rem">≡ Anything you\'d like us to remember?</div><div class="section-sub">Add anything about your day that may be useful later.</div>', unsafe_allow_html=True)
                diary = st.text_area("Daily note", label_visibility="collapsed", placeholder="Example: I took my evening medicine late because we were travelling today.")

                visit_note = ""
                if has_appointment:
                    st.markdown("**After your appointment**")
                    visit_note = st.text_area("What did the doctor tell you today?")

                submitted = st.form_submit_button("☁  Save today's log", type="primary", use_container_width=True)

            if submitted:
                log = DailyLog(patient.id, today, checklist, mood or "", list(symptoms), symptom_note, diary.strip(), visit_note.strip(), datetime.now())
                db.save_daily_log(log)
                if checklist:
                    lines = "\n".join(f"- {c.label}: {c.status.value}" for c in checklist)
                    memory.save_entry(Entry(patient.id, f"Daily check-in for {today}:\n{lines}", role, EntryType.CHECKLIST))
                if mood or symptoms or symptom_note:
                    memory.save_entry(Entry(patient.id, f"Mood: {mood or 'not given'}. Symptoms: {', '.join(symptoms) or 'none'}. {symptom_note}".strip(), role, EntryType.SYMPTOM))
                if log.diary:
                    memory.save_entry(Entry(patient.id, log.diary, role, EntryType.DIARY))
                if log.visit_note:
                    memory.save_entry(Entry(patient.id, f"Patient's note after appointment: {log.visit_note}", role, EntryType.VISIT_NOTE))
                st.rerun()

with chat_col:
    with st.container(border=True, key="onko_chat_panel"):
        st.markdown(
            '<div class="chat-head"><div class="chat-head-row">'
            '<div class="chat-head-title"><span class="chat-head-icon">✣</span>Ask OnKo</div>'
            f'<span class="chat-indexed">● {f"{days_remembered} days indexed" if days_remembered else "just started"}</span></div>'
            '<p>Ask about appointments, medications, past symptoms, or lab results.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="memory-note">✦ <b>Using your care memory</b><br>OnKo recalls your approved plan and past check-ins.</div>', unsafe_allow_html=True)
        st.caption("Try asking")
        q1, q2 = st.columns(2)
        if q1.button("When is my next test?", use_container_width=True):
            st.session_state.pending_prompt = "When is my next test?"
        if q2.button("What did I report last week?", use_container_width=True):
            st.session_state.pending_prompt = "What did I report last week?"

        history = st.session_state.setdefault("chat_history", [])
        for msg in history:
            st.chat_message(msg["role"]).markdown(msg["text"])

        typed = st.chat_input("Ask about your care journey…")
        prompt = typed or st.session_state.pop("pending_prompt", None)
        if prompt:
            history.append({"role": "user", "text": prompt})
            st.chat_message("user").markdown(prompt)
            with st.chat_message("assistant"), st.spinner("Checking your care memory…"):
                try:
                    reply = chat.handle_message(patient.id, prompt, role)
                    (st.error if reply.is_emergency else st.markdown)(reply.text)
                    history.append({"role": "assistant", "text": reply.text})
                except Exception as e:
                    st.error(f"Something went wrong: {e}")

        st.markdown('<div class="source-chip">CARE MEMORY · patient-specific sources</div>', unsafe_allow_html=True)
        st.caption("OnKo organizes recorded information. Your care team makes medical decisions.")

app_footer()
