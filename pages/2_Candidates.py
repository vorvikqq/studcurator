"""Candidates list / browse page: search, filter, and jump into a candidate's card."""

import pandas as pd
import streamlit as st

import auth
import db
from common import compute_score_aggregates

st.set_page_config(page_title="Кандидати", layout="wide")

db.init_db()
user = auth.render_sidebar_user()
reviewer_name = user["display_name"]
is_admin = auth.is_admin()

st.title("Кандидати")

candidates_df = db.get_candidates_df()
if candidates_df.empty:
    st.info("Кандидатів ще не імпортовано.")
    st.page_link("pages/1_Import.py", label="Перейти до імпорту", icon="📥")
    st.stop()

scores_df = db.get_all_scores()
agg = compute_score_aggregates(scores_df)

df = candidates_df.merge(
    agg[["overall", "num_reviewers"]], left_on="candidate_id", right_index=True, how="left"
)
df["num_reviewers"] = df["num_reviewers"].fillna(0).astype(int)

my_scored_ids = set(scores_df.loc[scores_df["reviewer_name"] == reviewer_name, "candidate_id"])
df["scored_by_me"] = df["candidate_id"].isin(my_scored_ids)

programs = ["Всі"] + sorted(p for p in candidates_df["education_program"].unique() if p)
program_choice = st.selectbox("Освітня програма", programs)

search = st.text_input("Пошук за іменем, телеграмом або телефоном")

col1, col2 = st.columns(2)
with col1:
    scored_filter = st.radio(
        "Статус оцінювання (мною)",
        ["Всі", "Ще не оцінені мною", "Оцінені мною"],
        horizontal=True,
    )
with col2:
    courses = ["Всі"] + sorted((c for c in candidates_df["course"].unique() if c), key=str)
    course_choice = st.selectbox("Курс", courses)

filtered = df.copy()
if program_choice != "Всі":
    filtered = filtered[filtered["education_program"] == program_choice]
if course_choice != "Всі":
    filtered = filtered[filtered["course"] == course_choice]
if search.strip():
    s = search.strip().lower()
    mask = (
        filtered["full_name"].str.lower().str.contains(s, na=False)
        | filtered["telegram"].str.lower().str.contains(s, na=False)
        | filtered["phone"].str.lower().str.contains(s, na=False)
    )
    filtered = filtered[mask]
if scored_filter == "Ще не оцінені мною":
    filtered = filtered[~filtered["scored_by_me"]]
elif scored_filter == "Оцінені мною":
    filtered = filtered[filtered["scored_by_me"]]

filtered = filtered.sort_values("full_name")

st.caption(f"Знайдено кандидатів: {len(filtered)}")

display_cols = ["full_name", "telegram", "course", "education_program", "scored_by_me"]
rename_map = {
    "full_name": "ПІБ",
    "telegram": "Телеграм",
    "course": "Курс",
    "education_program": "Освітня програма",
    "scored_by_me": "Оцінено мною",
    "overall": "Середній бал",
    "num_reviewers": "Рецензентів",
}
# Aggregated scores across all reviewers stay hidden from regular reviewers so that
# nobody's own scoring is influenced by seeing others' — admins see everything.
if is_admin:
    display_cols += ["overall", "num_reviewers"]

display_df = filtered[display_cols].copy()
display_df["scored_by_me"] = display_df["scored_by_me"].map({True: "✅", False: "—"})
if is_admin:
    display_df["overall"] = pd.to_numeric(display_df["overall"], errors="coerce").map(
        lambda x: "—" if pd.isna(x) else f"{x:.2f}"
    )
display_df = display_df.rename(columns=rename_map)
st.dataframe(display_df, use_container_width=True, hide_index=True)

if len(filtered) > 0:
    ids = filtered["candidate_id"].tolist()
    labels = {
        row.candidate_id: f"{row.full_name} — {row.telegram or 'без телеграму'}"
        for row in filtered.itertuples()
    }
    selected = st.selectbox(
        "Обрати кандидата для перегляду / оцінювання",
        ids,
        format_func=lambda cid: labels[cid],
    )
    if st.button("Відкрити картку кандидата", type="primary"):
        st.session_state.selected_candidate_id = selected
        st.session_state.candidate_nav_ids = ids
        st.switch_page("pages/3_Candidate_Detail.py")
else:
    st.info("Жодного кандидата не знайдено за поточними фільтрами.")
