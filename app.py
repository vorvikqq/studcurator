"""Entry point: sets up the DB and renders the progress dashboard (default landing page)."""

import streamlit as st

import db
from common import render_sidebar_reviewer

st.set_page_config(page_title="Студкуратор — Дашборд", layout="wide")

db.init_db()
render_sidebar_reviewer()

st.title("Дашборд прогресу оцінювання")

try:
    candidates_df = db.get_candidates_df()
except Exception as e:
    st.error(f"Не вдалося завантажити кандидатів із бази даних: {e}")
    st.stop()

if candidates_df.empty:
    st.info(
        "Кандидатів ще не імпортовано. Перейдіть на сторінку **Import**, "
        "щоб завантажити `candidates.csv`."
    )
    st.page_link("pages/1_Import.py", label="Перейти до імпорту", icon="📥")
    st.stop()

scores_df = db.get_all_scores()

total = len(candidates_df)
scored_ids = set(scores_df["candidate_id"].unique()) if not scores_df.empty else set()
scored_count = len(scored_ids)

st.subheader("Загальний прогрес")
m1, m2, m3 = st.columns(3)
m1.metric("Всього кандидатів", total)
m2.metric("Оцінено хоча б раз", scored_count)
m3.metric("Ще не оцінено", total - scored_count)
st.progress(scored_count / total if total else 0)

st.divider()
st.subheader("Прогрес за освітньою програмою")

by_program = candidates_df.copy()
by_program["is_scored"] = by_program["candidate_id"].isin(scored_ids)
program_stats = (
    by_program.groupby("education_program")
    .agg(total=("candidate_id", "count"), scored=("is_scored", "sum"))
    .reset_index()
)
program_stats["remaining"] = program_stats["total"] - program_stats["scored"]
program_stats = program_stats.rename(
    columns={
        "education_program": "Освітня програма",
        "total": "Всього кандидатів",
        "scored": "Оцінено",
        "remaining": "Залишилось",
    }
).sort_values("Освітня програма")

st.dataframe(program_stats, use_container_width=True, hide_index=True)
st.bar_chart(program_stats.set_index("Освітня програма")["Оцінено"])

st.divider()
st.subheader("Прогрес за рецензентом")

if scores_df.empty:
    st.info("Ще немає жодної оцінки.")
else:
    reviewer_stats = (
        scores_df.groupby("reviewer_name")["candidate_id"]
        .nunique()
        .reset_index(name="Кандидатів оцінено")
        .rename(columns={"reviewer_name": "Рецензент"})
        .sort_values("Кандидатів оцінено", ascending=False)
    )
    st.dataframe(reviewer_stats, use_container_width=True, hide_index=True)
