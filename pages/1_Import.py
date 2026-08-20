"""Import / Setup page: (re)import candidates.csv into the database."""

from pathlib import Path

import pandas as pd
import streamlit as st

import db
from common import render_sidebar_reviewer
from import_data import build_column_mapping, import_dataframe, load_csv

st.set_page_config(page_title="Імпорт кандидатів", layout="wide")

db.init_db()
render_sidebar_reviewer()

st.title("Імпорт / налаштування")
st.write(
    "Завантажте файл, експортований із Google Forms, або покладіть його як "
    "`candidates.csv` у теку проєкту — він підхопиться автоматично."
)

default_path = Path(__file__).resolve().parent.parent / "candidates.csv"

uploaded = st.file_uploader("Завантажити CSV файл", type=["csv"])

source = None
if uploaded is not None:
    source = uploaded
elif default_path.exists():
    st.info(f"Знайдено файл `{default_path.name}` у теці проєкту.")
    source = default_path
else:
    st.warning(
        "Файл `candidates.csv` не знайдено в теці проєкту. Завантажте файл вручну вище."
    )

if source is not None:
    try:
        df, delimiter = load_csv(source)
    except Exception as e:
        st.error(f"Не вдалося прочитати CSV файл: {e}")
        st.stop()

    st.caption(
        f"Визначений роздільник: `{delimiter}` · рядків: {len(df)} · колонок: {len(df.columns)}"
    )

    mapping, unmapped, missing = build_column_mapping(list(df.columns))

    st.subheader("Зіставлення колонок")
    st.write(
        "Перевірте, що кожна колонка з CSV правильно зіставлена з внутрішнім полем, "
        "перш ніж імпортувати."
    )
    mapping_display = pd.DataFrame(
        [{"Колонка у CSV": raw, "Внутрішнє поле": field} for raw, field in mapping.items()]
    )
    st.dataframe(mapping_display, use_container_width=True, hide_index=True)

    if unmapped:
        st.caption(
            "Колонки без зіставлення (все одно збережуться у raw_row_json як резерв): "
            + ", ".join(unmapped)
        )
    if missing:
        st.warning("Не знайдено очікуваних полів: " + ", ".join(missing))

    if st.button("Імпортувати / оновити кандидатів", type="primary"):
        try:
            result = import_dataframe(df, mapping)
        except Exception as e:
            st.error(f"Помилка під час імпорту: {e}")
        else:
            db.get_candidates_df.clear()
            st.success(
                f"Імпортовано/оновлено {result.imported} із {result.total_rows} кандидатів. "
                "Існуючі оцінки збережено — повторний імпорт безпечний."
            )
            prog_df = pd.DataFrame(
                sorted(result.per_program.items()), columns=["Освітня програма", "Кількість"]
            )
            st.dataframe(prog_df, use_container_width=True, hide_index=True)

            if result.failed:
                st.error(f"Не вдалося обробити {len(result.failed)} рядків:")
                for idx, reason in result.failed:
                    st.write(f"- Рядок {idx}: {reason}")
