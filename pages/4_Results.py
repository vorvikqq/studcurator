"""Results / export page: aggregated scores per candidate, sortable, downloadable."""

import pandas as pd
import streamlit as st

import db
from common import CRITERIA, SCORE_COLUMNS, compute_score_aggregates, render_sidebar_reviewer

st.set_page_config(page_title="Результати", layout="wide")

db.init_db()
render_sidebar_reviewer()

st.title("Результати / експорт")

candidates_df = db.get_candidates_df()
if candidates_df.empty:
    st.info("Кандидатів ще не імпортовано.")
    st.page_link("pages/1_Import.py", label="Перейти до імпорту", icon="📥")
    st.stop()

scores_df = db.get_all_scores()
agg = compute_score_aggregates(scores_df)

results = candidates_df.merge(agg, left_on="candidate_id", right_index=True, how="left")
for col in SCORE_COLUMNS + ["overall"]:
    if col not in results.columns:
        results[col] = pd.NA
if "num_reviewers" not in results.columns:
    results["num_reviewers"] = 0
results["num_reviewers"] = results["num_reviewers"].fillna(0).astype(int)

programs = ["Всі"] + sorted(p for p in candidates_df["education_program"].unique() if p)
program_choice = st.selectbox("Освітня програма", programs)
if program_choice != "Всі":
    results = results[results["education_program"] == program_choice]

low_coverage_threshold = st.number_input(
    "Позначати кандидатів із кількістю рецензентів ≤", min_value=0, max_value=10, value=1
)

display_cols = ["full_name", "telegram", "education_program", "course"] + SCORE_COLUMNS + [
    "overall",
    "num_reviewers",
]
display = results[display_cols].copy()
rename_map = {
    "full_name": "ПІБ",
    "telegram": "Телеграм",
    "education_program": "Освітня програма",
    "course": "Курс",
    "overall": "Середній бал",
    "num_reviewers": "Рецензентів",
}
rename_map.update({f: l for f, l in CRITERIA})
display = display.rename(columns=rename_map)

numeric_cols = [l for _, l in CRITERIA] + ["Середній бал"]
display[numeric_cols] = display[numeric_cols].apply(pd.to_numeric, errors="coerce").round(2)

display = display.sort_values("Середній бал", ascending=False, na_position="last")

low_mask = display["Рецензентів"] <= low_coverage_threshold

# st.dataframe's interactive grid doesn't respect Styler.format()'s na_rep for the
# displayed values, so format missing numbers to "—" strings ourselves; the raw
# numeric `display` frame (not this one) is what gets exported to CSV.
display_view = display.copy()
display_view[numeric_cols] = display_view[numeric_cols].apply(
    lambda col: col.map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
)


def highlight_low(row: pd.Series) -> list[str]:
    if row["Рецензентів"] <= low_coverage_threshold:
        return ["background-color: #fff3cd"] * len(row)
    return [""] * len(row)


st.dataframe(
    display_view.style.apply(highlight_low, axis=1),
    use_container_width=True,
    hide_index=True,
)

low_count = int(low_mask.sum())
if low_count:
    st.warning(f"⚠️ {low_count} кандидатів мають {low_coverage_threshold} або менше оцінок.")

csv_bytes = display.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Завантажити CSV",
    data=csv_bytes,
    file_name="results.csv",
    mime="text/csv",
)
