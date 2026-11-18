from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_bind_host: str = "127.0.0.1"
    database_url: str = "postgresql+psycopg://hub@127.0.0.1:5432/wechat_hub"
    data_root: Path = Path(".local/data")
    import_max_bytes: int = Field(default=1_073_741_824, gt=0)
    upload_max_files: int = Field(default=5000, gt=0)
    enable_ocr: bool = False
    enable_asr: bool = False
    enable_embeddings: bool = False
    enable_llm: bool = False
    enable_odoo: bool = False
    odoo_url: str = ""
    odoo_database: str = ""
    odoo_username: str = ""
    odoo_api_key: SecretStr | None = None
    allow_external_ai: bool = False
    enable_object_storage: bool = False
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    worker_poll_seconds: float = Field(default=1.0, ge=0.1)
    ocr_data_dir: Path = Path("/usr/share/tesseract-ocr/5/tessdata")
    ocr_languages: str = Field(
        default="chi_sim+eng", pattern=r"^[a-z_]+(?:\+[a-z_]+)*$", max_length=100
    )
    processing_timeout_seconds: int = Field(default=120, ge=5, le=600)
    processing_max_pixels: int = Field(default=20_000_000, ge=1, le=40_000_000)
    processing_max_bytes: int = Field(default=33_554_432, ge=1, le=134_217_728)
    asr_model_dir: Path | None = None
    asr_language: str = Field(default="auto", pattern=r"^(auto|zh|en)$")
    asr_max_seconds: int = Field(default=180, ge=1, le=600)
    local_model_server: Path | None = None
    embedding_model_file: Path | None = None
    llm_model_file: Path | None = None
    llm_max_tokens: int = Field(default=512, ge=32, le=2048)

    @field_validator("database_url")
    @classmethod
    def allowed_database(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "sqlite+pysqlite://")):
            raise ValueError("Use PostgreSQL/psycopg; SQLite is only for isolated tests")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
