import base64
import hashlib
import hmac
import ipaddress
import secrets
import time
from typing import Iterable
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from config import Settings, settings

security = HTTPBasic(auto_error=False)
ADMIN_SESSION_COOKIE = "safetyhub_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60
ADMIN_LOGIN_PATH = "/admin/login.html"
PUBLIC_ADMIN_STATIC_PATHS = {ADMIN_LOGIN_PATH, "/admin/css/style.css", "/admin/js/app.js"}
PUBLIC_ADMIN_API_PATHS = {"/admin/api/login", "/admin/api/logout"}


class AdminStaticAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/admin") or path.startswith("/admin/api") or path in PUBLIC_ADMIN_STATIC_PATHS:
            return await call_next(request)
        active_settings = _get_active_settings(request)
        try:
            _validate_admin_ip(request, active_settings.admin_ip_whitelist)
            admin_user = _authenticated_admin_user(request, active_settings)
            request.state.admin_user = admin_user
        except HTTPException as exc:
            if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                next_path = quote(str(request.url.path), safe="/")
                return Response(
                    status_code=status.HTTP_302_FOUND,
                    headers={"Location": f"{ADMIN_LOGIN_PATH}?next={next_path}"},
                )
            headers = exc.headers or {}
            return Response(str(exc.detail), status_code=exc.status_code, headers=headers)
        return await call_next(request)


class AdminStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        _set_admin_static_cache_headers(path, response)
        return response


async def require_admin_access(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    if request.url.path in PUBLIC_ADMIN_API_PATHS:
        return
    active_settings = _get_active_settings(request)
    _validate_admin_ip(request, active_settings.admin_ip_whitelist)
    admin_user = _authenticated_admin_user(request, active_settings, credentials)
    request.state.admin_user = admin_user


def create_admin_session_cookie(admin_user: str, active_settings: Settings) -> str:
    issued_at = str(int(time.time()))
    payload = f"{admin_user}:{issued_at}"
    signature = _session_signature(payload, active_settings)
    return f"{payload}:{signature}"


def clear_admin_session_cookie(response: Response) -> None:
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/admin")


def set_admin_session_cookie(
    response: Response, admin_user: str, active_settings: Settings, *, secure: bool | None = None
) -> None:
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        create_admin_session_cookie(admin_user, active_settings),
        max_age=ADMIN_SESSION_MAX_AGE,
        httponly=True,
        secure=secure if secure is not None else active_settings.is_production,
        samesite="lax",
        path="/admin",
    )


def validate_admin_login(username: str, password: str, active_settings: Settings) -> bool:
    if not active_settings.admin_password:
        return False
    username_valid = secrets.compare_digest(username, active_settings.admin_username)
    password_valid = secrets.compare_digest(password, active_settings.admin_password)
    return username_valid and password_valid


def _set_admin_static_cache_headers(path: str, response: Response) -> None:
    normalized_path = path.strip("/")
    if normalized_path == "" or normalized_path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store"
        return
    if normalized_path.endswith(".js") or normalized_path.endswith(".css"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"


def _get_active_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", settings)


def _authenticated_admin_user(
    request: Request,
    active_settings: Settings,
    credentials: HTTPBasicCredentials | None = None,
) -> str:
    if credentials is not None:
        _validate_admin_credentials(credentials, active_settings)
        return credentials.username
    session_user = _admin_user_from_session_cookie(request, active_settings)
    if session_user:
        return session_user
    credentials = _credentials_from_authorization(request.headers.get("authorization", ""))
    _validate_admin_credentials(credentials, active_settings)
    return credentials.username if credentials else ""


def _admin_user_from_session_cookie(request: Request, active_settings: Settings) -> str:
    cookie_value = request.cookies.get(ADMIN_SESSION_COOKIE, "")
    if not cookie_value:
        return ""
    username, issued_at, signature = _split_session_cookie(cookie_value)
    if not username or not issued_at or not signature:
        return ""
    payload = f"{username}:{issued_at}"
    expected_signature = _session_signature(payload, active_settings)
    if not secrets.compare_digest(signature, expected_signature):
        return ""
    try:
        issued_at_seconds = int(issued_at)
    except ValueError:
        return ""
    if issued_at_seconds + ADMIN_SESSION_MAX_AGE < int(time.time()):
        return ""
    if not secrets.compare_digest(username, active_settings.admin_username):
        return ""
    return username


def _split_session_cookie(cookie_value: str) -> tuple[str, str, str]:
    parts = cookie_value.split(":", 2)
    if len(parts) != 3:
        return "", "", ""
    return parts[0], parts[1], parts[2]


def _session_signature(payload: str, active_settings: Settings) -> str:
    secret = active_settings.admin_password or active_settings.app_name
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _validate_admin_ip(request: Request, whitelist: Iterable[str]) -> None:
    whitelist = list(whitelist)
    if not whitelist:
        return
    client_host = request.client.host if request.client else ""
    if not client_host or not _ip_allowed(client_host, whitelist):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access denied")


def _ip_allowed(client_host: str, whitelist: Iterable[str]) -> bool:
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        client_ip = None
    for item in whitelist:
        if secrets.compare_digest(client_host, item):
            return True
        if client_ip is None:
            continue
        try:
            if client_ip in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


def _validate_admin_credentials(credentials: HTTPBasicCredentials | None, active_settings: Settings) -> None:
    if credentials is None or not validate_admin_login(credentials.username, credentials.password, active_settings):
        raise _unauthorized()


def _credentials_from_authorization(authorization: str) -> HTTPBasicCredentials | None:
    scheme, _, encoded = authorization.partition(" ")
    if not scheme or not encoded or scheme.lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None
    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return HTTPBasicCredentials(username=username, password=password)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )
