"""Shared UI helpers and constants used across pages."""

from __future__ import annotations

import pandas as pd

# Numeric (1-5) criteria, in the order they should appear in the scoring form.
# These are the only criteria that go into the overall average.
NUMERIC_CRITERIA: list[tuple[str, str]] = [
    ("score_oss_experience", "Досвід в ОСС та знання про нього"),
    ("score_form_answers", "Бали за відповіді у формі"),
    ("score_interview_presentation", "Презентація себе на співбесіді"),
    ("score_case_answers", "Відповіді на кейси"),
]
NUMERIC_SCORE_COLUMNS = [field for field, _ in NUMERIC_CRITERIA]

# Non-numeric criteria: recorded per reviewer, shown separately, excluded from the average.
CURATOR_EXPERIENCE_FIELD = "curator_experience_confirmed"
CURATOR_EXPERIENCE_LABEL = "Досвід студкураторства"
LOCATION_FIELD = "location_text"
LOCATION_LABEL = "Місцезнаходження"


def compute_score_aggregates(scores_df: pd.DataFrame) -> pd.DataFrame:
    """Per-candidate mean of each numeric criterion, overall mean, reviewer count,
    curator-experience vote count, and last reported location.

    Returns a DataFrame indexed by candidate_id. Empty (but correctly columned)
    if there are no scores yet, so merges elsewhere just produce NaN/0.
    """
    if scores_df.empty:
        empty_cols = {
            col: pd.Series(dtype="float64") for col in NUMERIC_SCORE_COLUMNS + ["overall"]
        }
        empty_cols["num_reviewers"] = pd.Series(dtype="int64")
        empty_cols["curator_experience_votes"] = pd.Series(dtype="float64")
        empty_cols["location"] = pd.Series(dtype="object")
        return pd.DataFrame(empty_cols)

    df = scores_df.copy()
    df["overall"] = df[NUMERIC_SCORE_COLUMNS].mean(axis=1)
    agg = df.groupby("candidate_id").agg(
        **{f: (f, "mean") for f in NUMERIC_SCORE_COLUMNS},
        overall=("overall", "mean"),
        num_reviewers=("reviewer_name", "nunique"),
        curator_experience_votes=(CURATOR_EXPERIENCE_FIELD, "sum"),
    )

    last_location = (
        df[df[LOCATION_FIELD].fillna("").str.strip() != ""]
        .sort_values("updated_at")
        .groupby("candidate_id")[LOCATION_FIELD]
        .last()
    )
    agg["location"] = last_location
    agg["location"] = agg["location"].fillna("")
    return agg
