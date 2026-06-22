from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ArchivePayload:
    request_id: str
    model: str = ""
    capability: str = "chat"
    prompt_original: Any = None
    prompt_desensitized: Any = None
    response: Any = None
    is_stream: bool = False
    is_blocked: bool = False
    is_desensitized: bool = False
    action_taken: str = "passed"
    blocked_rule_id: str = ""
    matched_rule_ids: list[str] | None = None
    user_id: str = ""
    api_key_id: str = ""
    approval_id: str = ""
    file_ids: list[str] | None = None
    image_metadata: Any = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
