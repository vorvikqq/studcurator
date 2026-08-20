"""Shared UI helpers and constants used across pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import db

CRITERIA: list[tuple[str, str]] = [
    ("score_form_answers", "Бали за відповіді у формі"),
    ("score_curator_experience", "Досвід кураторства"),
    ("score_interview_presentation", "Презентація себе на співбесіді"),
    ("score_oss_experience", "Досвід в ОСС та знання про нього"),
    ("score_location", "Місцезнаходження"),
    ("score_case_answers", "Відповіді на кейси"),
]
SCORE_COLUMNS = [field for field, _ in CRITERIA]


def render_sidebar_reviewer() -> str:
    st.sidebar.markdown("## Хто оцінює")
    known_names = db.get_reviewer_names()

    if "reviewer_name" not in st.session_state:
        st.session_state.reviewer_name = ""

    other_label = "+ Інше ім'я..."
    options = known_names + [other_label]

    if known_names:
        if st.session_state.reviewer_name in known_names:
            default_index = known_names.index(st.session_state.reviewer_name)
        else:
            default_index = len(options) - 1
        choice = st.sidebar.selectbox("Ваше ім'я", options, index=default_index)
        if choice == other_label:
            name = st.sidebar.text_input(
                "Введіть ваше ім'я",
                value=st.session_state.reviewer_name
                if st.session_state.reviewer_name not in known_names
                else "",
            )
        else:
            name = choice
    else:
        name = st.sidebar.text_input("Введіть ваше ім'я", value=st.session_state.reviewer_name)

    st.session_state.reviewer_name = name.strip()
    if not st.session_state.reviewer_name:
        st.sidebar.warning("Вкажіть своє ім'я, щоб оцінювати кандидатів.")
    return st.session_state.reviewer_name


def compute_score_aggregates(scores_df: pd.DataFrame) -> pd.DataFrame:
    """Per-candidate mean of each criterion, overall mean, and reviewer count.

    Returns a DataFrame indexed by candidate_id. Empty (but correctly columned)
    if there are no scores yet, so merges elsewhere just produce NaN/0.
    """
    if scores_df.empty:
        empty_cols = {col: pd.Series(dtype="float64") for col in SCORE_COLUMNS + ["overall"]}
        empty_cols["num_reviewers"] = pd.Series(dtype="int64")
        return pd.DataFrame(empty_cols)

    df = scores_df.copy()
    df["overall"] = df[SCORE_COLUMNS].mean(axis=1)
    agg = df.groupby("candidate_id").agg(
        **{f: (f, "mean") for f in SCORE_COLUMNS},
        overall=("overall", "mean"),
        num_reviewers=("reviewer_name", "nunique"),
    )
    return agg
