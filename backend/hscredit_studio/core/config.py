"""应用配置（基于 Pydantic Settings）."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 应用基础 =====
    app_name: str = "HSCredit Workflow"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    secret_key: str = Field(min_length=32)
    log_level: str = "INFO"

    # ===== API 服务 =====
    api_v1_prefix: str = "/api/v1"
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    rate_limit_per_tenant: int = 100
    rate_limit_window_seconds: int = 60
    public_api_base_url: str = "http://localhost:8001"

    # ===== 数据库 =====
    database_url: str = "postgresql+asyncpg://hscredit:hscredit@localhost:5432/hscredit"
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_echo: bool = False

    # ===== Redis =====
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ===== 对象存储（S3 / MinIO / 本地后备）=====
    storage_provider: str = "s3"  # "s3" | "local"
    local_storage_dir: str = "./_storage"
    s3_endpoint: str = "http://localhost:9001"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio123"
    s3_bucket_prefix: str = "hscredit-dev"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    # ===== JWT =====
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ===== 沙箱（Phase 3 启用）=====
    sandbox_image: str = "hscredit-sandbox:latest"
    sandbox_timeout_sec: int = 300
    sandbox_memory_limit: str = "4g"
    sandbox_cpu_limit: str = "2"

    # ===== 可观测性 =====
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "hscredit-studio"

    # ===== 第三方集成（可选）=====
    slack_webhook_url: str | None = None
    wecom_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v):
        """支持环境变量用逗号分隔的字符串."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """获取单例配置."""
    return Settings()


# 全局单例
settings = get_settings()
