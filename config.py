from functools import lru_cache
import os
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
    upstream_timeout_pool: int = 5
    upstream_max_connections: int = 200
    upstream_max_keepalive_connections: int = 150
    upstream_keepalive_expiry: int = 30

    v1_max_inflight: int = 150
    v1_max_queue_size: int = 200
    v1_queue_timeout_seconds: float = 15
    admin_stats_cache_seconds: int = 10
    archive_queue_max_size: int = 5000
    archive_batch_size: int = 50
    archive_flush_interval_seconds: float = 1
    archive_max_payload_bytes: int = 262144

    rules_config_path: Path = Path("engine/rules_config.yaml")
    rules_reload_interval: int = 5
    scanner_order: list[str] = Field(default_factory=lambda: ["keyword", "regex"])
    scanner_fail_open: bool = False

    db_url: str = "sqlite+aiosqlite:///./data/safetyhub.db"
    archive_retention_days: int = 180
    audit_retention_days: int = 365
    data_governance_auto_coverage_enabled: bool = False
    data_governance_coverage_start_time: str = "02:00"
    data_governance_coverage_max_seconds: int = 600
    data_governance_coverage_max_records: int = 5000
    data_governance_coverage_batch_size: int = 200
    data_governance_coverage_batch_sleep_ms: int = 200
    data_governance_cleanup_batch_size: int = 1000
    system_disk_monitor_path: Path = Path("/")
    system_disk_monitor_container_path: Path = Path("/mnt/system-disk")
    data_disk_monitor_path: Path = Path("data")
    reports_enabled: bool = True
    reports_dir: Path = Path("data/reports")
    reports_retention_days: int = 90
    reports_runtime_sample_interval_minutes: int = 5
    reports_daily_generate_time: str = "02:00"
    reports_weekly_generate_time: str = "03:00"
    reports_monthly_generate_time: str = "04:00"
    reports_generation_timeout_seconds: int = 600
    image_asset_dir: Path = Path("data/image_assets")
    image_asset_max_size_mb: int = 20
    image_asset_download_timeout_seconds: int = 10
    data_encryption_enabled: bool = False
    data_encryption_key_env: str = "SAFETYHUB_DATA_KEY"
    allow_empty_api_keys_passthrough: bool = True
    stream_archive_max_bytes: int = 1024 * 1024
    key_provider_type: str = "passthrough"
    key_provider_admin_token: str = ""
    key_provider_base_url: str = ""
    key_provider_username: str = ""
    key_provider_password_env: str = "KEY_PROVIDER_PASSWORD"
    key_provider_auth_version: str = ""
    key_provider_default_remain_quota: int = 1000000
    key_provider_default_unlimited_quota: bool = True
    key_provider_timeout_seconds: int = 30
    key_provider_login_retries: int = 3
    key_provider_login_retry_delay_seconds: float = 10
    key_provider_request_retries: int = 3
    key_provider_request_retry_delay_seconds: float = 2

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

    def get_secret(self, env_name: str) -> str:
        value = os.getenv(env_name, "")
        if value:
            return value
        env_file = self.model_config.get("env_file")
        if not env_file:
            return ""
        configured_path = Path(str(env_file))
        env_paths = [configured_path] if configured_path.is_absolute() else [Path.cwd() / configured_path, Path(__file__).resolve().parent / configured_path]
        for env_path in dict.fromkeys(env_paths):
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, raw_value = stripped.split("=", 1)
                if key.strip() != env_name:
                    continue
                return raw_value.strip().strip('"').strip("'")
        return ""


def validate_startup_settings(settings: Settings) -> None:
    if not settings.is_production:
        return
    missing = []
    if not settings.upstream_url:
        missing.append("UPSTREAM_URL")
    if len(settings.admin_password) < 12:
        missing.append("ADMIN_PASSWORD")
    if not settings.get_secret(settings.data_encryption_key_env):
        missing.append(settings.data_encryption_key_env)
    if settings.allow_empty_api_keys_passthrough:
        missing.append("ALLOW_EMPTY_API_KEYS_PASSTHROUGH=false")
    if settings.key_provider_type == "oneapi_nanfu_yxai":
        if not settings.key_provider_base_url:
            missing.append("KEY_PROVIDER_BASE_URL")
        if not settings.key_provider_username:
            missing.append("KEY_PROVIDER_USERNAME")
        if not settings.get_secret(settings.key_provider_password_env):
            missing.append(settings.key_provider_password_env)
        if not settings.key_provider_auth_version:
            missing.append("KEY_PROVIDER_AUTH_VERSION")
    if missing:
        raise RuntimeError(f"Missing or unsafe production settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
