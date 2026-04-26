import os
from typing import Literal, Optional
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ================================
# Environment Setup
# ================================
load_dotenv(find_dotenv(), override=True)

# ================================
# Settings
# ================================

class Settings(BaseSettings):
    """
    Centralized configuration (Pydantic v2 compliant).
    Loads from .env and environment variables.
    """

    # ========================================
    # Pydantic v2 Config
    # ========================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    # ========================================
    # Server
    # ========================================
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    FRONTEND_DIR: str = "../frontend"
    API_PREFIX: str = "/api"
    API_VERSION: str = "v1"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ========================================
    # JWT
    # ========================================
    JWT_SECRET: str = "dev-secret-key-change-this-to-a-secure-32-char-min"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ========================================
    # Feature Flags
    # ========================================
    ENABLE_RAG: bool = True
    ENABLE_CACHING: bool = True
    ENABLE_TELEMETRY: bool = True
    ENABLE_PERSONA_REPORTS: bool = True

    # ========================================
    # LLM
    # ========================================
    LLM_PROVIDER: Literal["GOOGLE_GEMINI", "OPENAI", "ANTHROPIC"] = "OPENAI"
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    LLM_TEMPERATURE: float = Field(0.7, ge=0.0, le=2.0)
    LLM_MAX_TOKENS: int = Field(2048, ge=100)
    LLM_REQUEST_TIMEOUT: int = Field(30, ge=1)

    # ========================================
    # API KEYS
    # ========================================
    GOOGLE_GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None

    # ========================================
    # PROFILE
    # ========================================
    PROFILE_SOURCE: Literal["LEO_CDP", "POSTGRES", "MOCK_DATA"] = "MOCK_DATA"

    # ========================================
    # DB
    # ========================================
    PGSQL_DB_HOST: Optional[str] = None
    PGSQL_DB_PORT: int = 5432
    PGSQL_DB_NAME: Optional[str] = None
    PGSQL_DB_USER: Optional[str] = None
    PGSQL_DB_PASSWORD: Optional[str] = None

    # ========================================
    # REDIS
    # ========================================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = Field(6379, ge=1, le=65535)
    REDIS_DB: int = Field(0, ge=0, le=15)
    REDIS_PASSWORD: Optional[str] = None
    REDIS_CACHE_TTL: int = Field(3600, ge=60)

    # ========================================
    # OBSERVABILITY
    # ========================================
    PHOENIX_COLLECTOR_ENDPOINT: Optional[str] = "http://localhost:6006/v1/traces"
    OTEL_SERVICE_NAME: str = "ai-trip-planner-api"
    OTEL_EXPORTER_OTLP_TIMEOUT: int = Field(10, ge=1)

    # ========================================
    # CORS
    # ========================================
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True

    # ========================================
    # LOGGING
    # ========================================
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FILE: Optional[str] = "logs/app.log"

    # ========================================
    # DATA
    # ========================================
    PERSONA_DATA_DIR: str = "data/personas"
    REPORTS_DATA_DIR: str = "data/reports"
    TEMPLATES_DIR: str = "data/templates"
    MAX_REPORT_SIZE_MB: int = Field(10, ge=1)

    # ========================================
    # VALIDATORS (v2)
    # ========================================

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("❌ JWT_SECRET must be at least 32 characters long")

        if v == "super-secret-key-change-this" and os.getenv("ENVIRONMENT") == "production":
            raise ValueError("❌ JWT_SECRET must be changed in production")

        return v

    @field_validator("FRONTEND_DIR")
    @classmethod
    def validate_frontend_dir(cls, v: str) -> str:
        if not os.path.exists(v):
            raise ValueError(f"❌ FRONTEND_DIR does not exist: {v}")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors(cls, v):
        """
        Handle .env string like:
        CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]
        """
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @model_validator(mode="after")
    def validate_llm_keys(self):
        if self.LLM_PROVIDER == "OPENAI" and not self.OPENAI_API_KEY:
            raise ValueError("❌ OPENAI_API_KEY required")

        if self.LLM_PROVIDER == "GOOGLE_GEMINI" and not self.GOOGLE_GEMINI_API_KEY:
            raise ValueError("❌ GOOGLE_GEMINI_API_KEY required")

        if self.LLM_PROVIDER == "ANTHROPIC" and not self.ANTHROPIC_API_KEY:
            raise ValueError("❌ ANTHROPIC_API_KEY required")

        return self

    # ========================================
    # DERIVED
    # ========================================

    @property
    def DATABASE_URL(self) -> Optional[str]:
        if all([self.PGSQL_DB_HOST, self.PGSQL_DB_NAME, self.PGSQL_DB_USER, self.PGSQL_DB_PASSWORD]):
            return (
                f"postgresql://{self.PGSQL_DB_USER}:{self.PGSQL_DB_PASSWORD}"
                f"@{self.PGSQL_DB_HOST}:{self.PGSQL_DB_PORT}/{self.PGSQL_DB_NAME}"
            )
        return None

    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
        # ========================================
    # Debug Information
    # ========================================

    def log_config(self) -> None:
        """Log current configuration (secrets masked)."""
        config_dict = self.model_dump()
        
        # Mask sensitive keys
        sensitive_keys = [
            "JWT_SECRET", "OPENAI_API_KEY", "GOOGLE_GEMINI_API_KEY",
            "ANTHROPIC_API_KEY", "TAVILY_API_KEY", "REDIS_PASSWORD",
            "PGSQL_DB_PASSWORD", "LEO_API_KEY"
        ]
        
        for key in sensitive_keys:
            if key in config_dict and config_dict[key]:
                config_dict[key] = "***MASKED***"
        
        import json
        print("\n" + "="*60)
        print("📋 Application Configuration Loaded")
        print("="*60)
        print(json.dumps(config_dict, indent=2, default=str))
        print("="*60 + "\n")


# ========================================
# SINGLETON
# ========================================
@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()