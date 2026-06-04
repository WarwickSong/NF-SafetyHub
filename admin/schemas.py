from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int


class ArchiveSummary(BaseModel):
    id: int
    request_id: str
    user_id: str
    api_key_id: str
    model: str
    capability: str
    action_taken: str
    is_stream: bool
    is_blocked: bool
    is_desensitized: bool
    blocked_rule_id: str
    matched_rule_ids: list[str]
    created_at: datetime | None
    completed_at: datetime | None
    latency_ms: int


class ArchiveDetail(ArchiveSummary):
    messages_original: Any = Field(default_factory=list)
    messages_desensitized: Any = Field(default_factory=list)
    response: Any = None
    image_metadata: Any = Field(default_factory=dict)
    prompt_tokens: int
    completion_tokens: int


class ArchiveListResponse(BaseModel):
    items: list[ArchiveSummary]
    pagination: Pagination


class ArchiveStatsResponse(BaseModel):
    total: int
    blocked: int
    desensitized: int
    passed: int
    by_action: dict[str, int]
    by_model: dict[str, int]


class ImageAssetItem(BaseModel):
    id: int
    request_id: str
    source_index: int
    source_type: str
    source_url: str
    status: str
    local_path: str
    sha256: str
    mime_type: str
    size_bytes: int
    error: str
    created_at: datetime | None
    completed_at: datetime | None


class ImageAssetListResponse(BaseModel):
    items: list[ImageAssetItem]


class AuditSummary(BaseModel):
    id: int
    request_id: str
    user_id: str
    rule_id: str
    rule_name: str
    rule_level: str
    scanner_type: str
    action_taken: str
    created_at: datetime | None


class AuditDetail(AuditSummary):
    matched_snippet: str
    full_text_hash: str
    approval_id: str | None
    security_policy_id: str | None


class AuditListResponse(BaseModel):
    items: list[AuditSummary]
    pagination: Pagination


class TrendPoint(BaseModel):
    date: str
    requests: int
    hits: int
    blocked: int


class AdminStatsResponse(BaseModel):
    today_requests: int
    today_hits: int
    today_blocks: int
    total_requests: int
    total_hits: int
    total_blocks: int
    recent_trend: list[TrendPoint]


class ObservationItem(ArchiveDetail):
    pass


class ObservationListResponse(BaseModel):
    items: list[ObservationItem]


class AdminOperationItem(BaseModel):
    id: int
    request_id: str
    admin_user: str
    operation: str
    resource_type: str
    resource_id: str
    created_at: datetime | None


class AdminOperationListResponse(BaseModel):
    items: list[AdminOperationItem]
    pagination: Pagination


class RuleItem(BaseModel):
    id: str
    name: str
    type: str
    level: str
    enabled: bool
    description: str = ""


class RuleListResponse(BaseModel):
    items: list[RuleItem]


class RuleToggleRequest(BaseModel):
    enabled: bool


class RuleMutationResponse(BaseModel):
    status: str
    rule: RuleItem | None = None
    reloaded: bool = False


class RulesReloadResponse(BaseModel):
    status: str
    reloaded: bool


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    status: str
    message: str


class ApiKeyCreateRequest(BaseModel):
    name: str
    owner_user_id: str
    upstream_key: str = ""
    reuse_upstream_key: bool = True
    expires_at: datetime | None = None
    provider_name: str = "passthrough"
    owner_department: str | None = None
    cost_center: str | None = None
    create_mode: str = "manual"
    metadata: dict[str, Any] | None = None


class ApiKeyUpdateRequest(BaseModel):
    name: str | None = None
    expires_at: datetime | None = None


class ApiKeyReplaceRequest(BaseModel):
    new_upstream_key: str


class ApiKeyBulkReplaceRequest(BaseModel):
    csv_content: str


class ApiKeyItem(BaseModel):
    id: str
    name: str
    owner_user_id: str
    owner_department: str | None
    cost_center: str | None
    key_prefix: str
    key_suffix: str
    upstream_key_prefix: str | None
    provider_name: str
    status: str
    is_decoupled: bool
    created_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyItem]
    pagination: Pagination


class ApiKeyMutationResponse(BaseModel):
    status: str
    item: ApiKeyItem
    safetyhub_key: str | None = None


class ApiKeyRevealResponse(BaseModel):
    status: str
    api_key_id: str
    key: str
    key_prefix: str
    key_suffix: str


class ApiKeyBulkReplaceItem(BaseModel):
    identifier: str
    status: str
    message: str
    api_key_id: str = ""


class ApiKeyBulkReplaceResponse(BaseModel):
    status: str
    items: list[ApiKeyBulkReplaceItem]


class PlaceholderResponse(BaseModel):
    status: str = "reserved"
    message: str
