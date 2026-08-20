"""CSV loading and fuzzy header-mapping logic for the Google Forms export."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import pandas as pd

import db

APOSTROPHES = re.compile(r"[\'’ʼ‘`]")
WHITESPACE = re.compile(r"\s+")

# Priority-ordered mapping rules: (internal_field, [required substrings, ALL must match]).
# Order matters: more specific/unique keywords are checked first so they claim their
# header before a more generic keyword (checked later) can steal it.
MAPPING_RULES: list[tuple[str, list[str]]] = [
    ("timestamp", ["позначка часу"]),
    ("full_name", ["піб"]),
    ("phone", ["телефон"]),
    ("telegram", ["telegram"]),
    ("course", ["курс"]),
    ("education_program", ["освітня програма"]),
    ("case_1", ["посвяти"]),
    ("case_2", ["тримаються окремо"]),
    ("case_3", ["відрахуватися"]),
    ("case_4", ["не виходить на звязок"]),
    ("curator_experience_text", ["залученість"]),
    ("has_curator_experience", ["студкуратор"]),
    ("oss_experience_text", ["досвід", "осс"]),
    ("knows_oss", ["осс"]),
    ("likes_about_sp", ["подобається"]),
    ("what_would_tell_first_year", ["розповів"]),
    ("consent", ["згод"]),
]

EXPECTED_FIELDS = [rule[0] for rule in MAPPING_RULES]


def normalize_header(header: str) -> str:
    h = APOSTROPHES.sub("", header)
    h = h.casefold()
    h = WHITESPACE.sub(" ", h).strip()
    return h


def build_column_mapping(
    headers: list[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """Returns (raw_header -> internal_field mapping, unmapped headers, missing expected fields)."""
    normalized = {h: normalize_header(h) for h in headers}
    claimed: set[str] = set()
    mapping: dict[str, str] = {}

    for internal_field, required_substrings in MAPPING_RULES:
        for raw_header in headers:
            if raw_header in claimed:
                continue
            norm = normalized[raw_header]
            if all(sub in norm for sub in required_substrings):
                mapping[raw_header] = internal_field
                claimed.add(raw_header)
                break

    unmapped = [h for h in headers if h not in claimed]
    matched_fields = set(mapping.values())
    missing = [f for f in EXPECTED_FIELDS if f not in matched_fields]
    return mapping, unmapped, missing


def detect_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;")
        return dialect.delimiter
    except csv.Error:
        # Fallback heuristic: whichever delimiter is more frequent on the header line.
        first_line = sample_text.splitlines()[0] if sample_text else ""
        return ";" if first_line.count(";") > first_line.count(",") else ","


def load_csv(source: Union[str, Path, object]) -> tuple[pd.DataFrame, str]:
    """Loads the CSV from a path or an uploaded file-like object, auto-detecting the delimiter."""
    if hasattr(source, "read"):
        raw_bytes = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
        text = raw_bytes.decode("utf-8-sig") if isinstance(raw_bytes, bytes) else raw_bytes
    else:
        text = Path(source).read_text(encoding="utf-8-sig")

    sample = "\n".join(text.splitlines()[:5])
    delimiter = detect_delimiter(sample)

    import io

    df = pd.read_csv(
        io.StringIO(text),
        sep=delimiter,
        dtype=str,
        keep_default_na=False,
        engine="python",
    )
    df = df.fillna("")
    return df, delimiter


def make_candidate_id(full_name: str, telegram: str) -> str:
    def norm(value: str) -> str:
        value = APOSTROPHES.sub("", value or "")
        value = value.strip().lstrip("@").casefold()
        value = WHITESPACE.sub(" ", value)
        return value

    key = f"{norm(full_name)}|{norm(telegram)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class ImportResult:
    total_rows: int
    imported: int
    per_program: dict = field(default_factory=dict)
    failed: list = field(default_factory=list)


def import_dataframe(df: pd.DataFrame, mapping: dict[str, str]) -> ImportResult:
    per_program: dict[str, int] = {}
    failed: list[tuple[int, str]] = []
    imported = 0

    for idx, row in df.iterrows():
        raw_row = row.to_dict()
        mapped: dict[str, str] = {}
        for raw_header, internal_field in mapping.items():
            mapped[internal_field] = str(raw_row.get(raw_header, "")).strip()

        full_name = mapped.get("full_name", "").strip()
        telegram = mapped.get("telegram", "").strip()

        if not full_name:
            failed.append((idx, "Порожнє ПІБ — рядок пропущено"))
            continue

        candidate_id = make_candidate_id(full_name, telegram)
        program = mapped.get("education_program", "").strip() or "Не вказано"

        candidate = {col: mapped.get(col, "") for col in db.CANDIDATE_COLUMNS}
        candidate["candidate_id"] = candidate_id
        candidate["full_name"] = full_name
        candidate["education_program"] = program
        candidate["raw_row_json"] = json.dumps(raw_row, ensure_ascii=False)

        try:
            db.upsert_candidate(candidate)
        except Exception as e:  # noqa: BLE001 - surfaced to the user, not swallowed
            failed.append((idx, str(e)))
            continue

        imported += 1
        per_program[program] = per_program.get(program, 0) + 1

    return ImportResult(
        total_rows=len(df), imported=imported, per_program=per_program, failed=failed
    )
