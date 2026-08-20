"""Admin panel: create, list, and remove reviewer/admin accounts."""

import streamlit as st

import auth
import db

st.set_page_config(page_title="Адмін-панель", layout="wide")

db.init_db()
current = auth.render_sidebar_user()
auth.require_admin()

st.title("Адмін-панель")

st.subheader("Створити акаунт")
with st.form("create_user", clear_on_submit=True):
    display_name = st.text_input("Ім'я")
    username = st.text_input("Логін")
    password = st.text_input("Пароль", type="password")
    role = st.selectbox("Роль", ["reviewer", "admin"], format_func=lambda r: "Рецензент" if r == "reviewer" else "Адміністратор")
    submitted = st.form_submit_button("Створити", type="primary")

if submitted:
    username_clean = username.strip()
    if not username_clean or not display_name.strip():
        st.error("Заповніть ім'я та логін.")
    elif len(password) < 6:
        st.error("Пароль має містити щонайменше 6 символів.")
    else:
        salt, password_hash = auth.make_credentials(password)
        try:
            db.create_user(username_clean, display_name.strip(), salt, password_hash, role)
        except Exception as e:
            st.error(f"Не вдалося створити акаунт (можливо, такий логін вже існує): {e}")
        else:
            st.success(f"Акаунт «{username_clean}» створено.")

st.divider()
st.subheader("Акаунти")

users_df = db.list_users()
if users_df.empty:
    st.info("Акаунтів ще немає.")
else:
    display_df = users_df.rename(
        columns={
            "username": "Логін",
            "display_name": "Ім'я",
            "role": "Роль",
            "created_at": "Створено",
        }
    )
    display_df["Роль"] = display_df["Роль"].map({"admin": "Адміністратор", "reviewer": "Рецензент"})
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    deletable = [u for u in users_df["username"] if u != current["username"]]
    if deletable:
        to_delete = st.selectbox("Видалити акаунт", deletable)
        if st.button("Видалити", type="secondary"):
            try:
                db.delete_user(to_delete)
            except Exception as e:
                st.error(f"Не вдалося видалити акаунт: {e}")
            else:
                st.success(f"Акаунт «{to_delete}» видалено.")
                st.rerun()
    st.caption("Власний акаунт видалити не можна.")
