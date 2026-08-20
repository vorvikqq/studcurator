"""SQLite setup and data-access helpers for the curator scoring app."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent / "curator_app.db"

CANDIDATE_COLUMNS = [
    "candidate_id",
    "full_name",
    "telegram",
    "phone",
    "course",
    "education_program",
    "has_curator_experience",
    "curator_experience_text",
    "knows_oss",
    "oss_experience_text",
    "likes_about_sp",
    "what_would_tell_first_year",
    "case_1",
    "case_2",
    "case_3",
    "case_4",
    "consent",
    "raw_row_json",
]

# Numeric (1-5) criteria that go into the overall average.
NUMERIC_SCORE_FIELDS = [
    "score_oss_experience",
    "score_form_answers",
    "score_interview_presentation",
    "score_case_answers",
]
# Non-numeric criteria: recorded per (candidate, reviewer) but kept out of the average.
CURATOR_EXPERIENCE_FIELD = "curator_experience_confirmed"  # boolean (0/1)
LOCATION_FIELD = "location_text"  # free text

SCORE_FIELDS = NUMERIC_SCORE_FIELDS + [CURATOR_EXPERIENCE_FIELD, LOCATION_FIELD]


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidates (
            candidate_id TEXT PRIMARY KEY,
            full_name TEXT,
            telegram TEXT,
            phone TEXT,
            course TEXT,
            education_program TEXT,
            has_curator_experience TEXT,
            curator_experience_text TEXT,
            knows_oss TEXT,
            oss_experience_text TEXT,
            likes_about_sp TEXT,
            what_would_tell_first_year TEXT,
            case_1 TEXT,
            case_2 TEXT,
            case_3 TEXT,
            case_4 TEXT,
            consent TEXT,
            raw_row_json TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
            reviewer_name TEXT NOT NULL,
            score_oss_experience INTEGER,
            score_form_answers INTEGER,
            score_interview_presentation INTEGER,
            score_case_answers INTEGER,
            curator_experience_confirmed INTEGER,
            location_text TEXT,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scores_candidate_reviewer
        ON scores(candidate_id, reviewer_name);
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'reviewer')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def upsert_candidate(candidate: dict) -> None:
    conn = get_connection()
    placeholders = ", ".join(f":{c}" for c in CANDIDATE_COLUMNS)
    update_clause = ", ".join(
        f"{c}=excluded.{c}" for c in CANDIDATE_COLUMNS if c != "candidate_id"
    )
    conn.execute(
        f"""
        INSERT INTO candidates ({', '.join(CANDIDATE_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(candidate_id) DO UPDATE SET {update_clause};
        """,
        candidate,
    )
    conn.commit()


@st.cache_data
def get_candidates_df() -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM candidates", conn)


def get_candidate_by_id(candidate_id: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
    )
    return cur.fetchone()


def upsert_score(
    candidate_id: str, reviewer_name: str, scores: dict, comment: str
) -> None:
    conn = get_connection()
    params = {
        "candidate_id": candidate_id,
        "reviewer_name": reviewer_name,
        "comment": comment,
        **{field: scores[field] for field in SCORE_FIELDS},
    }
    set_clause = ", ".join(f"{f}=excluded.{f}" for f in SCORE_FIELDS)
    conn.execute(
        f"""
        INSERT INTO scores (
            candidate_id, reviewer_name, {', '.join(SCORE_FIELDS)}, comment,
            created_at, updated_at
        )
        VALUES (
            :candidate_id, :reviewer_name, {', '.join(f':{f}' for f in SCORE_FIELDS)},
            :comment, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(candidate_id, reviewer_name) DO UPDATE SET
            {set_clause},
            comment=excluded.comment,
            updated_at=CURRENT_TIMESTAMP;
        """,
        params,
    )
    conn.commit()


def get_all_scores() -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM scores", conn)


def get_scores_for_candidate(candidate_id: str) -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql_query(
        "SELECT * FROM scores WHERE candidate_id = ? ORDER BY reviewer_name",
        conn,
        params=(candidate_id,),
    )


def get_reviewer_score(candidate_id: str, reviewer_name: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT * FROM scores WHERE candidate_id = ? AND reviewer_name = ?",
        (candidate_id, reviewer_name),
    )
    return cur.fetchone()


def create_user(
    username: str, display_name: str, salt: str, password_hash: str, role: str
) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO users (username, display_name, salt, password_hash, role)
        VALUES (?, ?, ?, ?, ?);
        """,
        (username, display_name, salt, password_hash, role),
    )
    conn.commit()


def get_user(username: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()


def count_users() -> int:
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) AS c FROM users")
    return cur.fetchone()["c"]


def list_users() -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql_query(
        "SELECT username, display_name, role, created_at FROM users ORDER BY username COLLATE NOCASE",
        conn,
    )


def delete_user(username: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
