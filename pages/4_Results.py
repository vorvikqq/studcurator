"""Results / export page: aggregated scores per candidate, sortable, downloadable."""

import io

import pandas as pd
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
    compute_score_aggregates,
)

st.set_page_config(page_title="Результати", layout="wide")

db.init_db()
auth.render_sidebar_user()
auth.require_admin()

st.title("Результати / експорт")

candidates_df = db.get_candidates_df()
if candidates_df.empty:
    st.info("Кандидатів ще не імпортовано.")
    st.page_link("pages/1_Import.py", label="Перейти до імпорту", icon="📥")
    st.stop()

scores_df = db.get_all_scores()
agg = compute_score_aggregates(scores_df)

results = candidates_df.merge(agg, left_on="candidate_id", right_index=True, how="left")
for col in NUMERIC_SCORE_COLUMNS + ["overall", "curator_experience_votes"]:
    if col not in results.columns:
        results[col] = pd.NA
if "num_reviewers" not in results.columns:
    results["num_reviewers"] = 0
if "location" not in results.columns:
    results["location"] = ""
results["num_reviewers"] = results["num_reviewers"].fillna(0).astype(int)
results["location"] = results["location"].fillna("")


def format_curator_experience(row: pd.Series) -> str:
    if not row["num_reviewers"]:
        return "—"
    votes = int(row["curator_experience_votes"]) if pd.notna(row["curator_experience_votes"]) else 0
    return f"{votes}/{row['num_reviewers']}"


results["curator_experience_display"] = results.apply(format_curator_experience, axis=1)

programs = ["Всі"] + sorted(p for p in candidates_df["education_program"].unique() if p)
program_choice = st.selectbox("Освітня програма", programs)
if program_choice != "Всі":
    results = results[results["education_program"] == program_choice]

low_coverage_threshold = st.number_input(
    "Позначати кандидатів із кількістю рецензентів ≤", min_value=0, max_value=10, value=1
)

display_cols = ["full_name", "telegram", "education_program", "course"] + NUMERIC_SCORE_COLUMNS + [
    "overall",
    "curator_experience_display",
    "location",
    "num_reviewers",
]
display = results[display_cols].copy()
rename_map = {
    "full_name": "ПІБ",
    "telegram": "Телеграм",
    "education_program": "Освітня програма",
    "course": "Курс",
    "overall": "Середній бал",
    "curator_experience_display": CURATOR_EXPERIENCE_LABEL,
    "location": LOCATION_LABEL,
    "num_reviewers": "Рецензентів",
}
rename_map.update({f: l for f, l in NUMERIC_CRITERIA})
display = display.rename(columns=rename_map)

numeric_cols = [l for _, l in NUMERIC_CRITERIA] + ["Середній бал"]
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


def sanitize_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names: <=31 chars, no [ ] : * ? / \\, and unique within the workbook."""
    invalid = set("[]:*?/\\")
    cleaned = "".join(c for c in (name or "").strip() if c not in invalid) or "Без імені"
    cleaned = cleaned[:31]
    candidate = cleaned
    i = 2
    while candidate in used:
        suffix = f" ({i})"
        candidate = cleaned[: 31 - len(suffix)] + suffix
        i += 1
    used.add(candidate)
    return candidate


def build_excel_by_reviewer(
    overview_df: pd.DataFrame, scores_for_export: pd.DataFrame, candidates_df: pd.DataFrame
) -> bytes:
    """One overview sheet + one sheet per reviewer with just their own scores."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        overview_df.to_excel(writer, sheet_name="Загальні результати", index=False)
        used_names = {"Загальні результати"}

        if not scores_for_export.empty:
            merged = scores_for_export.merge(
                candidates_df[["candidate_id", "full_name", "telegram", "course", "education_program"]],
                on="candidate_id",
                how="left",
            )
            reviewer_cols = ["full_name", "telegram", "course", "education_program"] + NUMERIC_SCORE_COLUMNS + [
                CURATOR_EXPERIENCE_FIELD,
                LOCATION_FIELD,
                "comment",
            ]
            reviewer_rename = {
                "full_name": "ПІБ",
                "telegram": "Телеграм",
                "course": "Курс",
                "education_program": "Освітня програма",
                CURATOR_EXPERIENCE_FIELD: CURATOR_EXPERIENCE_LABEL,
                LOCATION_FIELD: LOCATION_LABEL,
                "comment": "Коментар",
            }
            reviewer_rename.update({f: l for f, l in NUMERIC_CRITERIA})

            for reviewer in sorted(merged["reviewer_name"].dropna().unique()):
                sheet_df = merged.loc[merged["reviewer_name"] == reviewer, reviewer_cols].copy()
                sheet_df[CURATOR_EXPERIENCE_FIELD] = sheet_df[CURATOR_EXPERIENCE_FIELD].map(
                    {1: "Так", 0: "Ні"}
                )
                sheet_df = sheet_df.rename(columns=reviewer_rename)
                sheet_name = sanitize_sheet_name(reviewer, used_names)
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


scores_for_export = scores_df[scores_df["candidate_id"].isin(results["candidate_id"])]
excel_bytes = build_excel_by_reviewer(display, scores_for_export, candidates_df)
st.download_button(
    "Завантажити Excel (окремий аркуш на кожного рецензента)",
    data=excel_bytes,
    file_name="results_by_reviewer.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
