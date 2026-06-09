from proxy.upstream_router import UpstreamRouter


def test_upstream_route_builds_chat_completions_url():
    router = UpstreamRouter("https://relay.example.com/base", timeout_connect=3, timeout_read=30)

    route = router.resolve(model="gpt-test")

    assert route.base_url == "https://relay.example.com/base"
    assert route.timeout_connect == 3
    assert route.timeout_read == 30
    assert route.build_url("/v1/chat/completions") == "https://relay.example.com/base/v1/chat/completions"
