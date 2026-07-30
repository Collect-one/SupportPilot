from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SupportPilot"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./support_pilot.db"
    jwt_secret: str = "local-development-secret-change-before-production"
    access_token_minutes: int = 480
    auto_create_tables: bool = True
    seed_demo: bool = True
    upload_dir: Path = Path("./uploads")
    demo_knowledge_dir: Path = Path("../docs/demo-knowledge")
    app_base_url: str = "http://localhost:8080"
    environment: str = "development"
    demo_mode: bool = True
    max_upload_bytes: int = 20 * 1024 * 1024
    embedding_dimensions: int = 1024
    retrieval_threshold: float = 0.42
    model_timeout_seconds: float = 30.0
    worker_lease_seconds: int = 300

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_enable_thinking: bool = False
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    feishu_webhook_url: str | None = None
    feishu_webhook_secret: str | None = None

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    )
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_safety(self):
        if self.environment.lower() == "production":
            if self.demo_mode or self.seed_demo or self.auto_create_tables:
                raise ValueError(
                    "生产环境必须关闭 DEMO_MODE、SEED_DEMO 和 AUTO_CREATE_TABLES"
                )
            if self.jwt_secret == "local-development-secret-change-before-production":
                raise ValueError("生产环境必须配置独立 JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
