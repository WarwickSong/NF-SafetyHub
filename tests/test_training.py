from storage.archive import ArchivePayload
from storage.training import _extract_assistant_response, _normalize_messages


def test_extract_assistant_response_from_non_stream_archive_body():
    payload = {"content": '{"choices":[{"message":{"content":"hello   world"}}]}'}
    assert _extract_assistant_response(payload) == "hello world"


def test_extract_assistant_response_ignores_truncated_stream():
    payload = {"stream": True, "message_content": "partial", "truncated": True}
    assert _extract_assistant_response(payload) == ""


def test_normalize_messages_keeps_structured_roles_and_content():
    messages = [{"role": "user", "content": "  hello\nworld  "}]
    assert _normalize_messages(messages) == [{"role": "user", "content": "hello world"}]


def test_training_candidate_payload_shape_keeps_prompt_and_response_separate():
    payload = ArchivePayload(
        request_id="req_1",
        prompt_original=[{"role": "user", "content": "hello"}],
        prompt_desensitized=[{"role": "user", "content": "hello"}],
        response={"content": '{"choices":[{"message":{"content":"answer"}}]}'},
    )
    assert _normalize_messages(payload.prompt_desensitized) == [{"role": "user", "content": "hello"}]
    assert _extract_assistant_response(payload.response) == "answer"
