"""FastAPI routes for the existing MySQL-backed RetailMind account services."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
import os
from typing import Any, Literal

import mysql.connector
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from .service import AuthService, AuthenticationError, UserProfile

COOKIE_NAME = "retailmind_session"
SESSION_LIFETIME_SECONDS = 8 * 60 * 60


def database_connection():
    required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    if any(not os.getenv(name) for name in required):
        raise AuthenticationError("MySQL connection settings are unavailable.")
    password = os.environ["MYSQL_PASSWORD"]
    try:
        port = int(os.environ["MYSQL_PORT"])
    except ValueError as error:
        raise AuthenticationError("MySQL connection settings are unavailable.") from error
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=port,
        user=os.environ["MYSQL_USER"],
        password=password,
        database=os.environ["MYSQL_DATABASE"],
        connection_timeout=8,
    )


def auth_service() -> AuthService:
    return AuthService(database_connection)


API_TOKEN = os.environ.get("RETAILMIND_API_TOKEN")


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    import secrets

    if API_TOKEN and not secrets.compare_digest(authorization or "", f"Bearer {API_TOKEN}"):
        raise HTTPException(status_code=401, detail="A valid backend token is required.")


def _safe_profile(user: UserProfile) -> dict:
    return asdict(user)


def _cookie_secure() -> bool:
    """Honour an explicit override, then known HTTPS deployments.

    Never force Secure on plain HTTP (for example localhost) or the browser will
    silently drop the session cookie. Production HTTPS environments should set
    RETAILMIND_COOKIE_SECURE=true.
    """
    explicit = os.getenv("RETAILMIND_COOKIE_SECURE", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    if os.getenv("VERCEL_ENV") in {"production", "preview"}:
        return True
    return os.getenv("RETAILMIND_PUBLIC_ORIGIN", "").strip().lower().startswith("https://")


def _set_session_cookie(response: Response, session_id: str, secret: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=f"{session_id}.{secret}",
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/", httponly=True, samesite="lax")


def _session_pair(cookie_value: str | None) -> tuple[str, str]:
    if not cookie_value or "." not in cookie_value:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    session_id, secret = cookie_value.split(".", 1)
    if not session_id or not secret or len(cookie_value) > 512:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return session_id, secret


def _raise_auth_error(error: AuthenticationError, *, fallback_status: int = 422) -> None:
    message = str(error)
    if message.startswith("Owner administrator"):
        status = 403
    elif message.startswith("Session") or message == "Account is unavailable.":
        status = 401
    elif "temporarily unavailable" in message or "connection settings" in message:
        status = 503
    elif message == "Invalid email or password.":
        status = 401
    else:
        status = fallback_status
    raise HTTPException(status_code=status, detail=message) from error


def require_authenticated_user(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> UserProfile:
    session_id, secret = _session_pair(session_cookie)
    try:
        return auth_service().validate_user_session(session_id, secret)
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=401)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RegistrationRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=12, max_length=1024)


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    phone: str | None = Field(default=None, max_length=32)


class PasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class GoalInput(BaseModel):
    id: int | None = Field(default=None, gt=0)
    goal_name: str = Field(min_length=1, max_length=150)
    period_start: date
    period_end: date
    target_sales: float = Field(gt=0)
    target_profit: float | None = Field(default=None, ge=0)
    target_category: str | None = Field(default=None, max_length=100)


class ReportInput(BaseModel):
    report_name: str = Field(min_length=1, max_length=150)
    report_type: Literal["overview", "sales", "profitability", "products", "customers", "inventory", "forecast", "custom"]
    filters: dict = Field(default_factory=dict)


class PreferencesInput(BaseModel):
    currency: Literal["INR", "USD", "EUR", "GBP"] = "INR"
    date_format: Literal["DD MMM YYYY", "MM/DD/YYYY", "YYYY-MM-DD"] = "DD MMM YYYY"
    default_period: Literal["7d", "30d", "90d", "12m"] = "30d"
    compact_mode: bool = False


router = APIRouter(prefix="/api", dependencies=[Depends(require_api_token)])


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response) -> dict:
    service = auth_service()
    try:
        user = service.login(payload.email, payload.password)
        session = service.create_user_session(user.id, SESSION_LIFETIME_SECONDS)
    except AuthenticationError as error:
        if str(error) == "Invalid email or password.":
            service.record_login_failure(payload.email)
        _raise_auth_error(error, fallback_status=401)
    _set_session_cookie(response, session.id, session.secret)
    return {"user": _safe_profile(user), "role": service.get_current_role(user.id)}


@router.post("/auth/register", status_code=201)
def register(payload: RegistrationRequest, response: Response) -> dict:
    service = auth_service()
    try:
        user = service.register(payload.full_name, payload.email, payload.phone, payload.password)
        session = service.create_user_session(user.id, SESSION_LIFETIME_SECONDS)
    except AuthenticationError as error:
        _raise_auth_error(error)
    _set_session_cookie(response, session.id, session.secret)
    return {"user": _safe_profile(user), "role": service.get_current_role(user.id)}


@router.get("/auth/session")
def current_session(user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        role = auth_service().get_current_role(user.id)
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)
    return {"user": _safe_profile(user), "role": role}


@router.post("/auth/logout")
def logout(
    response: Response,
    user: UserProfile = Depends(require_authenticated_user),
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> dict:
    session_id, _ = _session_pair(session_cookie)
    service = auth_service()
    try:
        service.revoke_user_session(user.id, session_id)
        service.logout(user.id)
    except AuthenticationError as error:
        _raise_auth_error(error)
    _clear_session_cookie(response)
    return {"ok": True}


@router.put("/auth/profile")
def update_profile(payload: ProfileUpdate, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        updated = auth_service().update_profile(user.id, payload.full_name, payload.email, payload.phone)
    except AuthenticationError as error:
        _raise_auth_error(error)
    return {"user": _safe_profile(updated)}


@router.post("/auth/password")
def update_password(
    payload: PasswordUpdate,
    response: Response,
    user: UserProfile = Depends(require_authenticated_user),
) -> dict:
    try:
        auth_service().change_password(user.id, payload.current_password, payload.new_password)
    except AuthenticationError as error:
        _raise_auth_error(error)
    _clear_session_cookie(response)
    return {"ok": True, "message": "Password updated. Sign in again with your new password."}


@router.get("/owner-admin/overview")
def owner_overview(user: UserProfile = Depends(require_authenticated_user)) -> dict:
    service = auth_service()
    try:
        service.require_owner_admin(user.id)
        return {
            "owner": service.get_assigned_owner_admin(),
            "accounts": service.list_owner_accounts(user.id),
            "sessions": service.list_owner_sessions(user.id),
            "events": service.list_owner_audit_events(user.id, limit=100),
            "event_counts": service.list_owner_event_counts(user.id),
        }
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.post("/owner-admin/sessions/{session_id}/revoke")
def owner_revoke_session(session_id: str, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        auth_service().revoke_session_as_owner(user.id, session_id)
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)
    return {"ok": True}


@router.get("/goals")
def list_goals(user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        return {"goals": auth_service().list_goals(user.id)}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.post("/goals", status_code=201)
def save_goal(payload: GoalInput, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="The goal end date must be on or after its start date.")
    try:
        auth_service().save_goal(user.id, payload.model_dump(mode="json"))
        return {"ok": True}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.delete("/goals/{goal_id}")
def remove_goal(goal_id: int, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        auth_service().delete_goal(user.id, goal_id)
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)
    return {"ok": True}


@router.get("/preferences")
def get_preferences(user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        return {"preferences": auth_service().get_preferences(user.id)}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.put("/preferences")
def save_preferences(payload: PreferencesInput, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        auth_service().save_preferences(user.id, payload.model_dump())
        return {"ok": True, "preferences": payload.model_dump()}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.get("/reports")
def list_reports(user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        reports = auth_service().list_reports(user.id)
        safe_reports = []
        for report in reports:
            item = dict(report)
            raw_filters = item.pop("filter_config", {})
            try:
                parsed_filters = json.loads(raw_filters) if isinstance(raw_filters, str) else raw_filters
                item["filters"] = parsed_filters if isinstance(parsed_filters, dict) else {}
            except (TypeError, ValueError):
                item["filters"] = {}
            safe_reports.append(item)
        return {"reports": safe_reports}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.post("/reports", status_code=201)
def save_report(payload: ReportInput, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    filter_config = json.dumps(payload.filters, separators=(",", ":"), ensure_ascii=False)
    if len(filter_config) > 10_000:
        raise HTTPException(status_code=413, detail="Report filters must be smaller than 10 KB.")
    try:
        auth_service().save_report(user.id, payload.report_name, payload.report_type, filter_config)
        return {"ok": True}
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)


@router.delete("/reports/{report_id}")
def remove_report(report_id: int, user: UserProfile = Depends(require_authenticated_user)) -> dict:
    try:
        auth_service().delete_report(user.id, report_id)
    except AuthenticationError as error:
        _raise_auth_error(error, fallback_status=503)
    return {"ok": True}
