import os
from typing import Literal, Optional
from functools import lru_cache

import re
from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ================================
# Environment Setup
# ================================
ENV_FILE_VARIABLE = "APP_ENV_FILE"
DEFAULT_ENV_FILE = ".env"


def get_env_file() -> str:
    """Return the dotenv file path selected for Settings."""
    return os.getenv(ENV_FILE_VARIABLE, DEFAULT_ENV_FILE)


load_dotenv(get_env_file(), override=True)

# Utility function to ensure required env variables are present
def require_env(key: str, default_value: str = None) -> str:
    '''Get an environment variable or raise an error if it's missing.'''
    value = os.getenv(key)
    if not value:
        if default_value is not None:
            return default_value
        raise ValueError(f"Missing required env: {key}")
    return value

# ========================================
# Database DSN Builder
# ========================================
def build_pg_dsn(prefix: str = "PGSQL_DB") -> str:
    """ Build PostgreSQL DSN for asyncpg driver from environment variables.

    Args:
        prefix (str, optional): Defaults to "PGSQL_DB".

    Returns:
        str: PGSQL DSN string for asyncpg driver, e.g.:
        postgresql+asyncpg://user:password@host:port/dbname
    """
    dsn = (
        f"postgresql+asyncpg://"
        f"{require_env(f'{prefix}_USER')}:"
        f"{require_env(f'{prefix}_PASSWORD')}@"
        f"{require_env(f'{prefix}_HOST', 'localhost')}:"
        f"{require_env(f'{prefix}_PORT', '5432')}/"
        f"{require_env(f'{prefix}_NAME')}"
    )
    return dsn

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
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    # ========================================
    # Server
    # ========================================
    HOST: str = "0.0.0.0"
    PORT: int = 8888
    PHOENIX_PORT: int = 6006
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
    
    # default tenant for multi-tenancy support (can be overridden by env var or during runtime)
    DEFAULT_TENANT_ID: str = "00000000-0000-0000-0000-000000000000"

    # ========================================
    # PROFILE 
    # ========================================
    PROFILE_SOURCE: Literal["LEO_CDP", "POSTGRES", "MOCK_DATA", "ARANGO"] = "MOCK_DATA"

    # ========================================
    # LEO CDP
    # ========================================
    LEO_API_KEY: Optional[str] = None
    LEO_API_VALUE: Optional[str] = None
    LEO_BASE_URL: Optional[str] = None

    # ========================================
    # DATABASE CONFIGURATION (PostgreSQL)
    # ========================================
    PGSQL_DB_HOST: Optional[str] = "localhost"
    PGSQL_DB_PORT: int = 5432
    PGSQL_DB_NAME: Optional[str] = None
    PGSQL_DB_USER: Optional[str] = None
    PGSQL_DB_PASSWORD: Optional[str] = None

    # ========================================
    # ARANGO DATABASE CONFIGURATION
    # ========================================
    ARANGO_HOST: Optional[str] = "http://localhost:8529"
    ARANGO_DB: Optional[str] = "leo_cdp_source"
    ARANGO_USER: Optional[str] = "root"
    ARANGO_PASSWORD: Optional[str] = None

    # ========================================
    # DRAMATIQ BROKER SETTINGS
    # ========================================
    DRAMATIQ_REDIS_URL: Optional[str] = "redis://localhost:6379/1"

    # Cron schedule for the profile synchronization task. 
    # Defaults to running daily at 2:00 AM ("0 2 * * *").
    DRAMATIQ_SYNC_PROFILES_CRON: str = "0 2 * * *"

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
    # SSO / AUTHENTICATION (Optional)
    # ========================================
    SSO_PROVIDER: Optional[str] = None
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # ========================================
    # CORS
    # ========================================
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8888"]
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
        """
        Validates JWT_SECRET for length, complexity, and production safety.
        """
        # 1. Length check
        if len(v) < 32:
            raise ValueError("❌ JWT_SECRET must be at least 32 characters long.")

        # 2. Production safety check
        # Avoid placeholder secrets in production
        is_prod = os.getenv("ENVIRONMENT", "").lower() == "production"
        insecure_values = ["change-this", "super-secret-key", "123456789", "password"]
        
        if is_prod and any(bad in v.lower() for bad in insecure_values):
            raise ValueError("❌ JWT_SECRET is insecure; change it before running in production.")

        # 3. Complexity check: Prevent simple repeated patterns (e.g., 'aaaaaaaaaaa...')
        # This regex checks if a character is repeated 8+ times consecutively
        if re.search(r"(.)\1{7,}", v):
            raise ValueError("❌ JWT_SECRET is too simple (contains repeating characters).")

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
        CORS_ORIGINS=["http://localhost:3000","http://localhost:8888"]
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
    def PGSQL_DATABASE_DSN(self) -> Optional[str]:
        if all([self.PGSQL_DB_HOST, self.PGSQL_DB_NAME, self.PGSQL_DB_USER, self.PGSQL_DB_PASSWORD]):
            dsn = (
                f"postgresql+asyncpg://"
                f"{self.PGSQL_DB_USER}:"
                f"{self.PGSQL_DB_PASSWORD}@"
                f"{self.PGSQL_DB_HOST}:"
                f"{self.PGSQL_DB_PORT}/"
                f"{self.PGSQL_DB_NAME}"
            )
            return dsn
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
            "PGSQL_DB_PASSWORD", "LEO_API_KEY", "LEO_API_VALUE",
            "ARANGO_PASSWORD", "GOOGLE_CLIENT_SECRET", "FACEBOOK_APP_SECRET",
            "GITHUB_CLIENT_SECRET"
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