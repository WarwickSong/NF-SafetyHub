from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.router import router
from config import Settings
from middleware.auth import AdminStaticAuthMiddleware, AdminStaticFiles


def create_test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.settings = settings
    return app


def create_static_test_app(settings: Settings) -> FastAPI:
    app = create_test_app(settings)
    app.add_middleware(AdminStaticAuthMiddleware)
    app.mount("/admin", AdminStaticFiles(directory="admin/static", html=True), name="admin")
    return app


def test_admin_api_requires_basic_auth():
    app = create_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        response = client.get("/admin/api/observations/recent")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


def test_admin_api_rejects_wrong_password():
    app = create_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        response = client.get(
            "/admin/api/observations/recent",
            auth=("admin", "wrong-password"),
        )

    assert response.status_code == 401


def test_admin_api_rejects_non_whitelisted_ip():
    app = create_test_app(
        Settings(
            admin_password="strong-local-password",
            admin_ip_whitelist=["10.0.0.1"],
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/api/observations/recent",
            auth=("admin", "strong-local-password"),
        )

    assert response.status_code == 403


def test_admin_api_allows_whitelisted_ip():
    app = create_test_app(
        Settings(
            admin_password="strong-local-password",
            admin_ip_whitelist=["testclient"],
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/admin/api/observations/recent",
            auth=("admin", "strong-local-password"),
        )

    assert response.status_code == 200


def test_admin_static_page_redirects_to_login_when_unauthenticated():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/admin/index.html")

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/login.html?next=/admin/index.html"


def test_admin_login_page_is_public():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        response = client.get("/admin/login.html")

    assert response.status_code == 200
    assert "SafetyHub 管理后台" in response.text


def test_admin_login_assets_are_public():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app, follow_redirects=False) as client:
        css_response = client.get("/admin/css/style.css")
        js_response = client.get("/admin/js/app.js")

    assert css_response.status_code == 200
    assert js_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert "javascript" in js_response.headers["content-type"]


def test_admin_static_assets_include_cache_control_headers():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        page_response = client.get("/admin/api_keys.html", auth=("admin", "strong-local-password"))
        js_response = client.get("/admin/js/app.js")
        css_response = client.get("/admin/css/style.css")

    assert page_response.status_code == 200
    assert page_response.headers["cache-control"] == "no-store"
    assert js_response.headers["cache-control"] == "no-cache, must-revalidate"
    assert css_response.headers["cache-control"] == "no-cache, must-revalidate"


def test_admin_frontend_write_actions_use_post_for_intranet_compatibility():
    script = open("admin/static/js/app.js", encoding="utf-8").read()

    assert 'method: "PATCH"' not in script
    assert 'method: "DELETE"' not in script
    assert "/toggle" in script
    assert "/update" in script
    assert "/delete" in script


def test_admin_static_page_allows_valid_basic_auth():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        response = client.get("/admin/index.html", auth=("admin", "strong-local-password"))

    assert response.status_code == 200
    assert "SafetyHub 管理后台" in response.text


def test_admin_login_sets_cookie_for_static_pages_and_api():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        login_response = client.post(
            "/admin/api/login",
            json={"username": "admin", "password": "strong-local-password"},
        )
        page_response = client.get("/admin/index.html")
        api_response = client.get("/admin/api/observations/recent")

    assert login_response.status_code == 200
    assert login_response.json()["status"] == "ok"
    assert "secure" not in login_response.headers["set-cookie"].lower()
    assert page_response.status_code == 200
    assert "SafetyHub 管理后台" in page_response.text
    assert api_response.status_code == 200


def test_admin_login_sets_secure_cookie_in_production():
    app = create_static_test_app(
        Settings(environment="production", admin_password="strong-local-password")
    )

    with TestClient(app) as client:
        response = client.post(
            "/admin/api/login",
            json={"username": "admin", "password": "strong-local-password"},
        )

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


def test_admin_login_rejects_wrong_password():
    app = create_static_test_app(Settings(admin_password="strong-local-password"))

    with TestClient(app) as client:
        response = client.post(
            "/admin/api/login",
            json={"username": "admin", "password": "wrong-password"},
        )

    assert response.status_code == 401
