"""Password hashing and Streamlit login/session helpers.

Reviewer identity now comes from a logged-in account (not free-text entry),
so scores can no longer be attributed to the wrong person by typo, and each
reviewer's scores are only visible to themselves and to admins.
"""

from __future__ import annotations

import hashlib
import secrets

import streamlit as st

import db

PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    ).hex()


def make_credentials(password: str) -> tuple[str, str]:
    """Returns (salt, password_hash) for a new or changed password."""
    salt = secrets.token_hex(16)
    return salt, _hash_password(password, salt)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return secrets.compare_digest(_hash_password(password, salt), expected_hash)


def current_user() -> dict | None:
    return st.session_state.get("user")


def is_admin() -> bool:
    user = current_user()
    return bool(user and user["role"] == "admin")


def logout() -> None:
    st.session_state.pop("user", None)


def _render_bootstrap_admin_form() -> None:
    st.title("Студкуратор")
    st.info("Акаунтів ще немає. Створіть перший акаунт адміністратора, щоб почати.")
    with st.form("bootstrap_admin"):
        display_name = st.text_input("Ваше ім'я")
        username = st.text_input("Логін")
        password = st.text_input("Пароль", type="password")
        password2 = st.text_input("Повторіть пароль", type="password")
        submitted = st.form_submit_button("Створити адмін-акаунт", type="primary")

    if submitted:
        username = username.strip()
        if not username or not display_name.strip():
            st.error("Заповніть ім'я та логін.")
        elif not password:
            st.error("Введіть пароль.")
        elif len(password) < 6:
            st.error("Пароль має містити щонайменше 6 символів.")
        elif password != password2:
            st.error("Паролі не співпадають.")
        else:
            salt, password_hash = make_credentials(password)
            try:
                db.create_user(username, display_name.strip(), salt, password_hash, "admin")
            except Exception as e:
                st.error(f"Не вдалося створити акаунт: {e}")
            else:
                st.success("Акаунт адміністратора створено. Тепер увійдіть.")
                st.rerun()


def _render_login_form() -> None:
    st.title("Студкуратор — Вхід")
    with st.form("login"):
        username = st.text_input("Логін")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Увійти", type="primary")

    if submitted:
        user = db.get_user(username.strip())
        if user is None or not verify_password(password, user["salt"], user["password_hash"]):
            st.error("Невірний логін або пароль.")
        else:
            st.session_state.user = {
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
            }
            st.rerun()


def require_login() -> dict:
    """Gates a page behind login. Renders login/bootstrap UI and stops if not authenticated."""
    user = current_user()
    if user is not None:
        return user

    if db.count_users() == 0:
        _render_bootstrap_admin_form()
    else:
        _render_login_form()
    st.stop()


def require_admin() -> None:
    if not is_admin():
        st.error("Ця сторінка доступна лише адміністратору.")
        st.stop()


def render_sidebar_user() -> dict:
    """Requires login, renders identity + logout in the sidebar, returns the user dict."""
    user = require_login()
    role_label = "адміністратор" if user["role"] == "admin" else "рецензент"
    st.sidebar.markdown(f"**{user['display_name']}**  \n_{role_label}_")
    if st.sidebar.button("Вийти"):
        logout()
        st.rerun()
    return user
