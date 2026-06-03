from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MessageArchive(Base):
    __tablename__ = "message_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="")
    api_key_id: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(128), index=True, default="")
    capability: Mapped[str] = mapped_column(String(64), default="chat")
    prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_original: Mapped[str] = mapped_column(Text, default="")
    prompt_desensitized: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    is_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_desensitized: Mapped[bool] = mapped_column(Boolean, default=False)
    action_taken: Mapped[str] = mapped_column(String(32), default="passed")
    blocked_rule_id: Mapped[str] = mapped_column(String(128), default="")
    matched_rule_ids: Mapped[str] = mapped_column(Text, default="")
    approval_id: Mapped[str] = mapped_column(String(128), default="")
    file_ids: Mapped[str] = mapped_column(Text, default="")
    image_metadata: Mapped[str] = mapped_column(Text, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


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
    full_text_hash: Mapped[str] = mapped_column(String(64), default="")
    action_taken: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdminOperation(Base):
    __tablename__ = "admin_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    admin_user: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(128), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
