from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://hub@127.0.0.1:5432/wechat_hub"
    data_root: Path = Path(".local/data")
    import_max_bytes: int = Field(default=1_073_741_824, gt=0)
    upload_max_files: int = Field(default=5000, gt=0)
    enable_ocr: bool = False
    enable_asr: bool = False
    enable_embeddings: bool = False
    enable_llm: bool = False
    enable_odoo: bool = False
    allow_external_ai: bool = False
    enable_object_storage: bool = False

    @field_validator("database_url")
    @classmethod
    def allowed_database(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "sqlite+pysqlite://")):
            raise ValueError("Use PostgreSQL/psycopg; SQLite is only for isolated tests")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
