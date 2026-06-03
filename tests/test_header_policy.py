from proxy.header_policy import build_upstream_headers


def test_build_upstream_headers_strips_hop_by_hop_and_internal_headers():
    headers = {
        "Host": "localhost",
        "Connection": "keep-alive",
        "Cookie": "session=secret",
        "Authorization": "Bearer token",
        "Content-Type": "application/json",
        "X-SafetyHub-Admin": "true",
    }

    upstream_headers = build_upstream_headers(headers, "req_test")

    assert "Host" not in upstream_headers
    assert "Connection" not in upstream_headers
    assert "Cookie" not in upstream_headers
    assert "X-SafetyHub-Admin" not in upstream_headers
    assert upstream_headers["Authorization"] == "Bearer token"
    assert upstream_headers["Content-Type"] == "application/json"
    assert upstream_headers["X-Request-ID"] == "req_test"


def test_build_upstream_headers_keeps_authorization_when_upstream_api_key_is_none():
    upstream_headers = build_upstream_headers(
        {"Authorization": "Bearer client-token", "Content-Type": "application/json"},
        "req_test",
        upstream_api_key=None,
    )

    assert upstream_headers["Authorization"] == "Bearer client-token"
    assert upstream_headers["Content-Type"] == "application/json"
    assert upstream_headers["X-Request-ID"] == "req_test"


def test_build_upstream_headers_replaces_authorization_when_upstream_api_key_is_set():
    upstream_headers = build_upstream_headers(
        {"Authorization": "Bearer client-token", "Content-Type": "application/json"},
        "req_test",
        upstream_api_key="sk-real",
    )

    assert upstream_headers["Authorization"] == "Bearer sk-real"
    assert upstream_headers["Content-Type"] == "application/json"
    assert upstream_headers["X-Request-ID"] == "req_test"
