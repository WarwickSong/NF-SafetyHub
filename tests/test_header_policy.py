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
