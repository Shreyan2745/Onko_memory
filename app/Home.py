"""Home: role + patient selection. Owner: Niya."""

import ui_common
from ui_common import app_footer, app_header, setup_page
import streamlit as st
from core import db, memory
from core.contracts import Role

setup_page("Role Selection")
patients = db.list_patients()
selected = patients[0] if patients else None
app_header("Role Selection", selected)

st.markdown('<div style="text-align:center;margin:2.2rem 0 1.8rem"><div class="eyebrow">Role Selection</div><div class="hero-title">Welcome to OnKo Memory</div><div class="hero-sub">One continuous memory for your care journey.<br>Preserving continuity across treatments, daily logs, and clinical visits so nothing is lost.</div></div>', unsafe_allow_html=True)

if not patients:
    st.info("No patients yet. Load the demo patient using the seed script.")
else:
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            st.markdown('<span class="badge">Daily Companion</span><div class="section-title" style="margin-top:1rem">Patient</div><div class="section-sub">Log your day, check off today\'s care items, record symptoms, and talk to your care companion.</div>', unsafe_allow_html=True)
            st.markdown('<div class="memory-note">✦ <b>LONGITUDINAL BUFFER</b><br>Remembers your daily logs, medicines, and questions.</div>', unsafe_allow_html=True)
            st.write("")
            if st.button("Continue as Patient  →", type="primary", use_container_width=True):
                st.session_state.role = Role.PATIENT
                st.session_state.patient = selected
                memory.ensure_bank(selected)
                st.switch_page("pages/2_Patient.py")
    with right:
        with st.container(border=True):
            st.markdown('<span class="badge">Clinician & Nurse</span><div class="section-title" style="margin-top:1rem">Care Team</div><div class="section-sub">Update care information, upload lab reports, write notes, and review what happened since the last visit.</div>', unsafe_allow_html=True)
            st.markdown('<div class="memory-note">⬟ <b>CLINICAL GOVERNANCE</b><br>Structured verification — nothing enters patient memory without your approval.</div>', unsafe_allow_html=True)
            st.write("")
            if st.button("Continue as Doctor / Nurse  →", use_container_width=True):
                st.session_state.role = Role.DOCTOR
                st.session_state.patient = selected
                memory.ensure_bank(selected)
                st.switch_page("pages/1_Doctor.py")

    st.write("")
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(f'<div class="eyebrow">▣ &nbsp; Active Patient Context &nbsp; • &nbsp; {selected.name} &nbsp; <code>{selected.id}</code></div><div style="font-size:.76rem;margin-top:.3rem">{selected.age} yrs &nbsp;·&nbsp; {selected.diagnosis or "Care journey"}<br><span style="color:#60766d">OnKo memory uses patient-specific verified records. All answers and daily careflows adapt to this approved plan.</span></div>', unsafe_allow_html=True)
        with c2:
            picked = st.selectbox("Change patient", patients, index=0, format_func=lambda p: f"{p.name} (ID {p.id})", label_visibility="collapsed")
            if picked.id != selected.id:
                st.session_state.patient = picked
                st.rerun()

app_footer()
