from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class TrainingConversation(Base):
    __tablename__ = "training_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    api_key_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    model: Mapped[str] = mapped_column(String(128), index=True, default="")
    capability: Mapped[str] = mapped_column(String(64), default="chat")
    messages: Mapped[str] = mapped_column(Text, default="")
    assistant_response: Mapped[str] = mapped_column(Text, default="")
    trajectory: Mapped[str] = mapped_column(Text, default="")
    trajectory_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    covered_by_conversation_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    analysis_status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    prompt_bytes: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    is_desensitized: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class DataGovernanceJob(Base):
    __tablename__ = "data_governance_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="running")
    requested_by: Mapped[str] = mapped_column(String(128), default="")
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    marked_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor_value: Mapped[str] = mapped_column(String(128), default="")
    config_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    rule_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    rule_name: Mapped[str] = mapped_column(String(256), default="")
    rule_level: Mapped[str] = mapped_column(String(32), index=True, default="")
    scanner_type: Mapped[str] = mapped_column(String(64), default="")
    matched_snippet: Mapped[str] = mapped_column(Text, default="")
    context_snippet: Mapped[str] = mapped_column(Text, default="")
    desensitized_snippet: Mapped[str] = mapped_column(Text, default="")
    full_text_hash: Mapped[str] = mapped_column(String(64), default="")
    action_taken: Mapped[str] = mapped_column(String(32), default="")
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    security_policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    source_index: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(32), index=True, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    local_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), default="")
    key_suffix: Mapped[str] = mapped_column(String(8), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    owner_user_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    owner_department: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    cost_center: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="active")
    provider_name: Mapped[str] = mapped_column(String(64), default="passthrough")
    upstream_route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upstream_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    upstream_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    upstream_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    safetyhub_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_decoupled: Mapped[bool] = mapped_column(Boolean, index=True, default=False)
    security_policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    approval_chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    api_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    capability: Mapped[str] = mapped_column(String(64), default="chat")
    rule_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    current_level: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class SecurityPolicy(Base):
    __tablename__ = "security_policies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_overrides: Mapped[str] = mapped_column(Text, default="{}")
    block_threshold: Mapped[str] = mapped_column(String(16), default="block")
    warn_to_block_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    immutable_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    inherit_from: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class ApprovalChain(Base):
    __tablename__ = "approval_chains"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    chain_definition: Mapped[str] = mapped_column(Text, default="[]")
    trigger_rule_levels: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_capabilities: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_policy: Mapped[str] = mapped_column(String(32), default="auto_reject")
    blocked_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AdminOperation(Base):
    __tablename__ = "admin_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    admin_user: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(128), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
