# Prompt for Claude Code

Copy everything below into Claude Code (in the project folder where you'll also place the exported CSV file).

---

## Context

I'm building an internal tool for evaluating candidates for a "student curator" (студкуратор) role at a university faculty. Candidates apply via a Google Form, and I export all responses as a single CSV file. Multiple reviewers will conduct interviews in parallel and need to score each candidate independently. I need a local web app to browse candidates and enter scores.

## Tech stack

- Python 3
- Streamlit for the UI
- SQLite for storing scores (so multiple reviewers writing at once doesn't corrupt data — use WAL mode)
- pandas for CSV handling

## Step 1 — Inspect the data

There is a file `candidates.csv` in the project folder (exported from Google Forms, UTF-8, comma or semicolon separated — detect automatically). Read its headers first and print them out before writing any mapping code, because the exact Ukrainian column names may vary slightly from what I describe below.

Expected columns (Ukrainian, approximate — match by fuzzy/substring matching, not exact string equality, since Google Forms may add timestamps or slightly reword headers):

1. Timestamp (Google Forms adds this automatically, usually first column)
2. ПІБ (full name)
3. Телеграм
4. Номер телефону
5. Курс (year of study)
6. Освітня програма (education program — **this is the primary grouping field**)
7. Чи є досвід студкуратора (yes/no)
8. Опис досвіду студкуратора (free text, may be empty)
9. Чи знайомий/ма з роботою ОСС КНУ (yes/no)
10. Опис досвіду/знань про ОСС КНУ/ФІТ (free text)
11. Що подобається в СП ФІТ (free text)
12. Що розповів би першокурснику про СП ФІТ (free text)
13. Кейс 1 — після посвяти, куди поведеш групу (free text)
14. Кейс 2 — студенти тримаються окремо (free text)
15. Кейс 3 — першокурсник хоче відрахуватися (free text)
16. Кейс 4 — студент не виходить на зв'язок добу (free text)
17. Згода на обробку даних (consent, usually yes/no)

Build a mapping/config dict from raw CSV column name → internal field name, and print it for confirmation before proceeding, so it's easy for me to fix if a column was misdetected.

## Step 2 — Data model

On first run, create a SQLite database `curator_app.db` with two tables:

**`candidates`** — one row per candidate, populated from the CSV import (re-importing should upsert by a stable key: use `ПІБ + Телеграм` combined, normalized/trimmed, as the dedup key — or a generated stable hash of those two fields as `candidate_id`).

Columns: `candidate_id` (PK), `full_name`, `telegram`, `phone`, `course`, `education_program`, `has_curator_experience`, `curator_experience_text`, `knows_oss`, `oss_experience_text`, `likes_about_sp`, `what_would_tell_first_year`, `case_1`, `case_2`, `case_3`, `case_4`, `consent`, `raw_row_json` (store the full original row as JSON as a fallback so no data is ever lost even if my mapping missed a column).

**`scores`** — one row per (candidate, reviewer) pair.

Columns: `id` (PK autoincrement), `candidate_id` (FK), `reviewer_name` (text), `score_form_answers` (int 1-5), `score_curator_experience` (int 1-5), `score_interview_presentation` (int 1-5), `score_oss_experience` (int 1-5), `score_location` (int 1-5), `score_case_answers` (int 1-5), `comment` (text, general impression), `created_at`, `updated_at`.

A `(candidate_id, reviewer_name)` unique constraint — if the same reviewer scores the same candidate again, it's an UPDATE (upsert), not a duplicate row. This lets multiple different reviewers score the same candidate independently, and their scores get averaged later.

## Step 3 — App structure

Use Streamlit's multipage app structure (`pages/` folder) or a sidebar radio to switch between these views:

### 3a. Import / Setup page
- File uploader (or auto-detect `candidates.csv` in folder) to (re)import the CSV into the `candidates` table.
- Show import summary: how many candidates found, how many per `education_program`, any rows that failed to parse.
- This should be safe to re-run without duplicating or losing existing scores (scores are keyed by candidate_id, which is stable across re-imports as long as name+telegram don't change).

### 3b. Reviewer identity
- At the top of the sidebar (visible on every page), a text input or selectbox "Хто оцінює" (reviewer name) — store in `st.session_state`. All scoring actions use this as `reviewer_name`. Persist the last used name in browser local storage isn't needed — session state is enough, but prefill a dropdown with previously-used reviewer names (query distinct `reviewer_name` from `scores` table) so people don't retype/typo their name each time.

### 3c. Dashboard / Progress page (this should be the default landing page)
Show:
- Total number of candidates.
- Overall progress: how many candidates have at least 1 score vs. 0 scores (progress bar + numbers), broken down **by education program** (a table or bar chart: program name | total candidates | scored | remaining).
- A breakdown by reviewer: how many candidates each reviewer has scored so far (table: reviewer_name | count).
- Optionally a simple bar chart (st.bar_chart) of candidates scored per education program.

### 3d. Candidates list / browse page
This is the main working page. Include:
- A search box that filters by name, telegram, or phone (substring match, case-insensitive).
- A filter dropdown for `education_program` (grouping is critical — make this prominent, e.g. as tabs or a selectbox at the top, defaulting to "all" but easy to narrow to one program at a time since programs are evaluated separately).
- A filter toggle: "show only not yet scored by me" / "show only scored by me" / "show all" (based on current reviewer_name in session).
- A filter for `course` (year) as a secondary optional filter.
- Results shown as a table or list of expandable cards, each showing: full name, telegram, course, education program, whether current reviewer already scored them (✅/—), and average score so far across all reviewers if any exist.
- Clicking/expanding a candidate opens their full profile (see 3e) inline or navigates to it.

### 3e. Candidate detail + scoring page
For a selected candidate, show:
- All their form answers, nicely formatted with labels (name, contacts, course, program, experience descriptions, all 4 case answers as separate labeled blocks so they're easy to read during/after the interview).
- Location/where-they-live info if present in the data (surface this clearly since it matters for scoring).
- A scoring form with the 7 criteria as sliders or selectboxes (1-5 each): Бали за відповіді у формі, Досвід кураторства, Презентація себе на співбесіді, Досвід в ОСС та знання про нього, Місцезнаходження, Відповіді на кейси, and a text area for Загальне враження (коментар).
- If the current reviewer already scored this candidate, pre-fill the form with their existing scores (so they can edit).
- A "Save score" button that upserts into the `scores` table.
- Below the form, show a read-only summary table of **all reviewers' scores** for this candidate so far (reviewer name, each criterion, comment), plus the average per criterion and overall average — so reviewers can see how others scored without it blocking their own independent input.
- Simple prev/next candidate navigation buttons (respecting the current filter/search context) so a reviewer can move through a list without going back to the list page each time.

### 3f. Results / export page
- A table of all candidates with their average score per criterion, overall average score, number of reviewers who scored them, and a link/expander to see full details — sortable by any column (especially by overall average, descending) and filterable by education program.
- A "Download CSV" button that exports this aggregated results table.
- Optionally highlight candidates with very few reviews (e.g. 0 or 1) so it's easy to spot who still needs more coverage.

## Step 4 — Practical details

- Use `st.set_page_config(layout="wide")` for more horizontal space, since case answers can be long.
- Enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`) on connection so concurrent reads/writes from multiple browser sessions don't lock each other out.
- Wrap all writes in try/except with a user-visible error message on failure (don't fail silently).
- Cache the CSV-derived candidates data appropriately (`st.cache_data`) but make sure scores are always read fresh (no caching, or short TTL) since they change constantly during parallel interviews.
- All UI text should be in Ukrainian (this is for a Ukrainian-speaking team), but code, comments, and variable names should be in English.
- Keep the code in a small number of well-organized files, e.g.: `app.py` (entry + dashboard), `db.py` (SQLite setup/helpers), `import_data.py` (CSV import logic), `pages/1_Candidates.py`, `pages/2_Candidate_Detail.py` (or equivalent — organize however fits Streamlit's multipage conventions best), `pages/3_Results.py`.
- Add a `requirements.txt` (streamlit, pandas) and a short `README.md` with: how to install (`pip install -r requirements.txt`), how to run (`streamlit run app.py`), where to put `candidates.csv`, and a one-paragraph explanation of how scoring/averaging works.

## Step 5 — After building

Run the app locally to confirm there are no errors on startup (even without a real CSV present, it should show a friendly "please import a CSV" state rather than crashing). Then give me instructions for:
1. Running it locally on my machine.
2. (Optional, mention briefly) how I could deploy it to Streamlit Community Cloud so other reviewers can access it via a link instead of everyone running it locally.

---

Ask me clarifying questions only if the CSV headers are genuinely ambiguous after inspection — otherwise proceed and build the full app.
