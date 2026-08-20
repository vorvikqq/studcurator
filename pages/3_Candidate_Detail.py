"""Candidate detail + scoring page."""

import streamlit as st

import auth
import db
from common import (
    CURATOR_EXPERIENCE_FIELD,
    CURATOR_EXPERIENCE_LABEL,
    LOCATION_FIELD,
    LOCATION_LABEL,
    NUMERIC_CRITERIA,
    NUMERIC_SCORE_COLUMNS,
)

st.set_page_config(page_title="Картка кандидата", layout="wide")

db.init_db()
user = auth.render_sidebar_user()
reviewer_name = user["display_name"]

st.title("Картка кандидата")

if not st.session_state.get("selected_candidate_id"):
    st.info("Спочатку оберіть кандидата на сторінці «Кандидати».")
    st.page_link("pages/2_Candidates.py", label="До списку кандидатів", icon="⬅️")
    st.stop()

candidate_id = st.session_state.selected_candidate_id
candidate = db.get_candidate_by_id(candidate_id)

if candidate is None:
    st.error("Кандидата не знайдено — можливо, дані було переімпортовано.")
    st.page_link("pages/2_Candidates.py", label="До списку кандидатів", icon="⬅️")
    st.stop()

nav_ids = st.session_state.get("candidate_nav_ids") or [candidate_id]
idx = nav_ids.index(candidate_id) if candidate_id in nav_ids else 0

nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
with nav_col1:
    if st.button("⬅️ Попередній", disabled=idx <= 0, use_container_width=True):
        st.session_state.selected_candidate_id = nav_ids[idx - 1]
        st.rerun()
with nav_col2:
    st.markdown(f"<div style='text-align:center'>Кандидат {idx + 1} з {len(nav_ids)}</div>", unsafe_allow_html=True)
with nav_col3:
    if st.button("Наступний ➡️", disabled=idx >= len(nav_ids) - 1, use_container_width=True):
        st.session_state.selected_candidate_id = nav_ids[idx + 1]
        st.rerun()

st.page_link("pages/2_Candidates.py", label="До списку кандидатів", icon="⬅️")

st.header(candidate["full_name"] or "(без імені)")

c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"**Телеграм:** {candidate['telegram'] or '—'}")
c2.markdown(f"**Телефон:** {candidate['phone'] or '—'}")
c3.markdown(f"**Курс:** {candidate['course'] or '—'}")
c4.markdown(f"**Освітня програма:** {candidate['education_program'] or '—'}")

st.markdown(f"**Згода на обробку даних:** {candidate['consent'] or '—'}")

st.subheader("Досвід студкураторства")
st.markdown(f"**Чи є досвід:** {candidate['has_curator_experience'] or '—'}")
st.write(candidate["curator_experience_text"] or "_Опис відсутній_")

st.subheader("Знання про ОСС КНУ/ФІТ")
st.markdown(f"**Чи знайомий/ма:** {candidate['knows_oss'] or '—'}")
st.write(candidate["oss_experience_text"] or "_Опис відсутній_")

st.subheader("Про СП ФІТ")
st.markdown("**Що подобається:**")
st.write(candidate["likes_about_sp"] or "—")
st.markdown("**Що розповів би першокурснику:**")
st.write(candidate["what_would_tell_first_year"] or "—")

st.subheader("Кейси")
case_labels = {
    "case_1": "Кейс 1 — після посвяти, куди поведеш групу",
    "case_2": "Кейс 2 — студенти тримаються окремо",
    "case_3": "Кейс 3 — першокурсник хоче відрахуватися",
    "case_4": "Кейс 4 — студент не виходить на зв'язок добу",
}
for field, label in case_labels.items():
    with st.expander(label, expanded=True):
        st.write(candidate[field] or "—")

st.divider()
st.subheader("Оцінювання")

existing = db.get_reviewer_score(candidate_id, reviewer_name)
with st.form("score_form"):
    values = {}
    for field, label in NUMERIC_CRITERIA:
        default = int(existing[field]) if existing and existing[field] is not None else 3
        values[field] = st.slider(label, 1, 5, default)

    curator_default = (
        bool(existing[CURATOR_EXPERIENCE_FIELD])
        if existing and existing[CURATOR_EXPERIENCE_FIELD] is not None
        else False
    )
    curator_experience = st.checkbox(CURATOR_EXPERIENCE_LABEL, value=curator_default)

    location_default = existing[LOCATION_FIELD] if existing and existing[LOCATION_FIELD] else ""
    location = st.text_input(LOCATION_LABEL, value=location_default)

    comment = st.text_area(
        "Загальне враження (коментар)",
        value=(existing["comment"] if existing and existing["comment"] else ""),
    )
    submitted = st.form_submit_button("Зберегти оцінку", type="primary")

values[CURATOR_EXPERIENCE_FIELD] = 1 if curator_experience else 0
values[LOCATION_FIELD] = location.strip()

if submitted:
    try:
        db.upsert_score(candidate_id, reviewer_name, values, comment)
    except Exception as e:
        st.error(f"Не вдалося зберегти оцінку: {e}")
    else:
        st.success("Оцінку збережено.")
        st.rerun()

# Other reviewers' scores are only visible to admins — reviewers score independently
# without seeing each other's assessments.
if auth.is_admin():
    st.divider()
    st.subheader("Оцінки всіх рецензентів")

    all_scores = db.get_scores_for_candidate(candidate_id)
    if all_scores.empty:
        st.info("Поки що ніхто не оцінив цього кандидата.")
    else:
        show_cols = ["reviewer_name"] + NUMERIC_SCORE_COLUMNS + [
            CURATOR_EXPERIENCE_FIELD,
            LOCATION_FIELD,
            "comment",
        ]
        show_df = all_scores[show_cols].copy()
        show_df[CURATOR_EXPERIENCE_FIELD] = show_df[CURATOR_EXPERIENCE_FIELD].map(
            {1: "Так", 0: "Ні"}
        )
        rename_map = {
            "reviewer_name": "Рецензент",
            "comment": "Коментар",
            CURATOR_EXPERIENCE_FIELD: CURATOR_EXPERIENCE_LABEL,
            LOCATION_FIELD: LOCATION_LABEL,
        }
        rename_map.update({f: l for f, l in NUMERIC_CRITERIA})
        show_df = show_df.rename(columns=rename_map)
        st.dataframe(show_df, use_container_width=True, hide_index=True)

        avg_row = all_scores[NUMERIC_SCORE_COLUMNS].mean()
        overall_avg = avg_row.mean()
        metric_cols = st.columns(len(NUMERIC_SCORE_COLUMNS) + 1)
        for i, (field, label) in enumerate(NUMERIC_CRITERIA):
            metric_cols[i].metric(label, f"{avg_row[field]:.2f}")
        metric_cols[-1].metric("Загальний середній", f"{overall_avg:.2f}")

        curator_votes = int(all_scores[CURATOR_EXPERIENCE_FIELD].sum())
        st.caption(
            f"{CURATOR_EXPERIENCE_LABEL}: {curator_votes}/{len(all_scores)} рецензентів "
            "підтвердили (не входить у середній бал)."
        )
