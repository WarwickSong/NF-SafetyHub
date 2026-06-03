from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LLM-SafetyHub"
    environment: str = "development"
    debug: bool = True

    upstream_url: str = ""
    upstream_timeout_connect: int = 10
    upstream_timeout_read: int = 120
    upstream_route_config_path: Path = Path("config/upstream_routes.yaml")

    rules_config_path: Path = Path("engine/rules_config.yaml")
    rules_reload_interval: int = 5
    scanner_order: list[str] = Field(default_factory=lambda: ["keyword", "regex"])

    db_url: str = "sqlite+aiosqlite:///./data/safetyhub.db"
    archive_retention_days: int = 180
    audit_retention_days: int = 365
    data_encryption_enabled: bool = False
    data_encryption_key_env: str = "SAFETYHUB_DATA_KEY"
    key_provider_type: str = "passthrough"
    key_provider_admin_token: str = ""

    admin_username: str = "admin"
    admin_password: str = ""
    admin_ip_whitelist: list[str] = Field(default_factory=list)

    webhook_url: str = ""
    webhook_type: str = "wecom"
    approval_webhook_url: str = ""
    approval_timeout_minutes: int = 30
    alert_silence_rule_minutes: int = 5
    alert_silence_user_minutes: int = 2
    alert_hourly_limit: int = 50

    request_max_body_mb: int = 20
    file_scan_enabled: bool = False
    file_max_size_mb: int = 50
    file_allowed_types: list[str] = Field(default_factory=lambda: ["txt", "md", "pdf", "docx", "xlsx", "csv"])

    uvicorn_workers: int = 4
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.lower().strip()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def validate_startup_settings(settings: Settings) -> None:
    if not settings.is_production:
        return
    missing = []
    if not settings.upstream_url:
        missing.append("UPSTREAM_URL")
    if len(settings.admin_password) < 12:
        missing.append("ADMIN_PASSWORD")
    if missing:
        raise RuntimeError(f"Missing or unsafe production settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
