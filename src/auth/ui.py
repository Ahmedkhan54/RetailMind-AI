"""Small Streamlit UI adapter; session values remain server-side in Streamlit."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
import mysql.connector
import pandas as pd
import streamlit as st
from .service import (
    OWNER_ADMIN_ROLE,
    SAFE_AUDIT_EVENTS,
    AuthService,
    AuthenticationError,
    UserProfile,
    UserSession,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def _ensure_env_loaded() -> None:
    if ENV_PATH.exists():
        for enc in ("utf-8", "windows-1252", "latin-1"):
            try:
                load_dotenv(dotenv_path=ENV_PATH, override=False, encoding=enc)
                break
            except Exception:
                continue


def get_db_config() -> dict[str, object]:
    _ensure_env_loaded()
    raw_password = os.getenv("MYSQL_PASSWORD")
    password = raw_password.strip(' \t\r\n"\'“”\x93\x94') if raw_password else None
    if not password:
        raise AuthenticationError(
            "MySQL password is not configured. Set MYSQL_PASSWORD in the root .env file before establishing a database connection."
        )
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": password,
        "database": os.getenv("MYSQL_DATABASE", "retail_sales_db"),
        "connection_timeout": 8,
    }


def _connection():
    return mysql.connector.connect(**get_db_config())


def service() -> AuthService:
    return AuthService(_connection)


def _store(user: UserProfile, session: UserSession | None = None) -> None:
    st.session_state["authenticated_user_id"] = user.id
    st.session_state["authenticated_session_version"] = user.session_version
    if session is not None:
        st.session_state["authenticated_session_id"] = session.id
        st.session_state["authenticated_session_secret"] = session.secret


def _clear_authentication() -> None:
    st.session_state.pop("authenticated_user_id", None)
    st.session_state.pop("authenticated_session_version", None)
    st.session_state.pop("authenticated_session_id", None)
    st.session_state.pop("authenticated_session_secret", None)
    st.session_state.pop("owner_monitor_access_logged", None)
    st.session_state.pop("audit_dashboard_accessed", None)
    # Uploaded data is session-only and must not survive logout/account changes.
    for key in list(st.session_state):
        if key.startswith(("uploaded_", "upload_", "data_upload_", "filter_", "audit_filter_fp_", "persistent_upload_")):
            st.session_state.pop(key, None)


def _establish_session(user: UserProfile) -> None:
    _store(user, service().create_user_session(user.id))


def require_authentication() -> UserProfile | None:
    # Test-only dependency injection. Both variables are required so a normal
    # deployment cannot accidentally enable it; production always validates DB state.
    if os.getenv("RETAIL_DASHBOARD_TEST_AUTH") == "1" and os.getenv("PYTEST_CURRENT_TEST"):
        return UserProfile(id=999, email="test@example.invalid", full_name="Test User", phone=None, account_status="active", session_version=1, created_at="test", last_login_at=None)
    session_id = st.session_state.get("authenticated_session_id")
    session_secret = st.session_state.get("authenticated_session_secret")
    if session_id and session_secret:
        try:
            return service().validate_user_session(session_id, session_secret)
        except AuthenticationError:
            _clear_authentication()
    st.title("RetailMind AI")
    tab_login, tab_register = st.tabs(["Sign in", "Create account"])
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            try:
                _establish_session(service().login(email, password))
                st.rerun()
            except AuthenticationError as error:
                service().record_login_failure(email)
                st.error(str(error))
    with tab_register:
        st.caption("New registrations create a standard user account. Role selection is not available.")
        with st.form("register_form"):
            name = st.text_input("Full name"); email = st.text_input("Email", key="register_email")
            phone = st.text_input("Phone (optional)"); password = st.text_input("Password", type="password", key="register_password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                _establish_session(service().register(name, email, phone, password))
                st.rerun()
            except AuthenticationError as error:
                st.error(str(error))
    return None


def profile_controls(user: UserProfile) -> None:
    with st.sidebar:
        st.divider(); st.caption(f"Signed in as {user.email}")
        if st.button("Sign out", key="logout"):
            session_id = st.session_state.get("authenticated_session_id")
            if session_id:
                try:
                    service().revoke_user_session(user.id, session_id)
                except AuthenticationError:
                    pass
            service().logout(user.id)
            _clear_authentication(); st.rerun()
        with st.expander("Profile"):
            st.write({"Account created": user.created_at, "Last login": user.last_login_at, "Status": user.account_status.title()})
            with st.form("profile_form"):
                name = st.text_input("Full name", value=user.full_name); email = st.text_input("Email", value=user.email); phone = st.text_input("Phone", value=user.phone or "")
                save = st.form_submit_button("Save profile")
            if save:
                try: service().update_profile(user.id, name, email, phone); st.success("Profile updated.")
                except AuthenticationError as error: st.error(str(error))
            with st.form("password_form"):
                current = st.text_input("Current password", type="password"); new = st.text_input("New password", type="password")
                change = st.form_submit_button("Change password")
            if change:
                try:
                    service().change_password(user.id, current, new)
                    session_id = st.session_state.get("authenticated_session_id")
                    if session_id:
                        try:
                            service().revoke_user_session(user.id, session_id)
                        except AuthenticationError:
                            pass
                    _clear_authentication()
                    st.success("Password changed. Please sign in again.")
                except AuthenticationError as error: st.error(str(error))


def render_owner_admin_monitor(user: UserProfile) -> None:
    """Owner-only monitoring. Authorization is re-checked in the database on every call."""
    if os.getenv("RETAIL_DASHBOARD_TEST_AUTH") == "1" and os.getenv("PYTEST_CURRENT_TEST"):
        return
    try:
        if not service().is_owner_admin(user.id):
            return
    except Exception:
        return
    with st.sidebar:
        st.caption("Owner administrator")
    with st.expander("Owner monitoring", expanded=False):
        st.caption("Live server-side view of registrations, sessions, and audit events. Passwords, hashes, and session secrets are never displayed.")
        _render_owner_admin_monitor_body(user)


def _render_owner_admin_monitor_body(user: UserProfile) -> None:
    try:
        if not st.session_state.get("owner_monitor_access_logged"):
            service().record_activity(user.id, "owner_admin_dashboard_accessed")
            st.session_state["owner_monitor_access_logged"] = True
        counts = service().list_owner_event_counts(user.id)
        accounts = service().list_owner_accounts(user.id)
        sessions = service().list_owner_sessions(user.id)
        event_filter = st.selectbox(
            "Audit event type",
            ["All events"] + sorted(SAFE_AUDIT_EVENTS),
            key="owner_audit_event_filter",
        )
        selected_event = None if event_filter == "All events" else event_filter
        events = service().list_owner_audit_events(user.id, selected_event)
    except AuthenticationError as error:
        st.error(str(error))
        return
    owner_count = sum(1 for row in accounts if row.get("assigned_role") == OWNER_ADMIN_ROLE)
    summary = st.columns(4)
    summary[0].metric("Registered accounts", f"{len(accounts):,}")
    summary[1].metric("Owner assignments", f"{owner_count:,}")
    summary[2].metric("Tracked sessions", f"{len(sessions):,}")
    summary[3].metric("Audit rows shown", f"{len(events):,}")
    st.subheader("Event totals")
    counts_frame = pd.DataFrame(counts)
    if counts_frame.empty:
        st.info("No audit events have been recorded yet.")
    else:
        st.dataframe(counts_frame, width="stretch", hide_index=True)
    st.subheader("Registrations")
    accounts_frame = pd.DataFrame(accounts)
    if accounts_frame.empty:
        st.info("No accounts are registered yet.")
    else:
        st.dataframe(accounts_frame, width="stretch", hide_index=True)
    st.subheader("Sessions")
    sessions_frame = pd.DataFrame(sessions)
    if sessions_frame.empty:
        st.info("No sessions are stored yet.")
    else:
        st.dataframe(sessions_frame, width="stretch", hide_index=True)
    st.subheader("Audit log")
    events_frame = pd.DataFrame(events)
    if events_frame.empty:
        st.info("No audit rows match this filter.")
    else:
        st.dataframe(events_frame, width="stretch", hide_index=True)
