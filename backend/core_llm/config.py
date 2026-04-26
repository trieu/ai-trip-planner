"""
Centralized configuration management for AI Trip Planner API.
Loads environment variables and provides type-safe configuration access.
"""

import os
from typing import Literal, Optional
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """
    Application settings loaded from .env file and environment variables.
    Uses Pydantic v2 for validation and type safety.
    """

    # ========================================
    # Server Configuration
    # ========================================
    HOST: str = Field(default="0.0.0.0", description="Server host address")
    PORT: int = Field(default=8000, description="Server port")
    WORKERS: int = Field(default=4, description="Number of worker processes")
    FRONTEND_DIR: str = Field(default="../frontend",
                              description="Path to frontend directory")
    API_PREFIX: str = Field(default="/api", description="API route prefix")
    API_VERSION: str = Field(default="v1", description="API version")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Application environment"
    )

    # ========================================
    # JWT Authentication Configuration
    # ========================================
    JWT_SECRET: str = Field(
        default="super-secret-key-change-this",
        description="Secret key for JWT token signing"
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithm for JWT token encoding"
    )
    JWT_EXPIRE_MINUTES: int = Field(
        default=60,
        description="JWT token expiration time in minutes"
    )
    JWT_REFRESH_EXPIRE_DAYS: int = Field(
        default=7,
        description="Refresh token expiration time in days"
    )

    # ========================================
    # Feature Flags
    # ========================================
    ENABLE_RAG: bool = Field(
        default=True,
        description="Enable Retrieval-Augmented Generation features"
    )
    ENABLE_CACHING: bool = Field(
        default=True,
        description="Enable Redis caching"
    )
    ENABLE_TELEMETRY: bool = Field(
        default=True,
        description="Enable OpenTelemetry tracing"
    )
    ENABLE_PERSONA_REPORTS: bool = Field(
        default=True,
        description="Enable customer persona report generation"
    )

    # ========================================
    # LLM Provider Configuration
    # ========================================
    LLM_PROVIDER: Literal["GOOGLE_GEMINI", "OPENAI", "ANTHROPIC"] = Field(
        default="OPENAI",
        description="Language model provider selection"
    )
    LLM_MODEL_NAME: str = Field(
        default="gpt-4o-mini",
        description="Model name for LLM provider"
    )
    EMBEDDING_MODEL_NAME: str = Field(
        default="text-embedding-3-small",
        description="Model name for embeddings"
    )
    LLM_TEMPERATURE: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM responses (0.0-2.0)"
    )
    LLM_MAX_TOKENS: int = Field(
        default=2048,
        ge=100,
        description="Maximum tokens for LLM responses"
    )
    LLM_REQUEST_TIMEOUT: int = Field(
        default=30,
        ge=1,
        description="Request timeout in seconds"
    )

    # ========================================
    # API Keys (External Services)
    # ========================================
    GOOGLE_GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API key"
    )
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key"
    )
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        description="Anthropic API key"
    )
    TAVILY_API_KEY: Optional[str] = Field(
        default=None,
        description="Tavily API key for enhanced search results"
    )

    # ========================================
    # Profile Source Configuration
    # ========================================
    PROFILE_SOURCE: Literal["LEO_CDP", "POSTGRES", "MOCK_DATA"] = Field(
        default="MOCK_DATA",
        description="Source for customer profile data"
    )

    # ========================================
    # LEO CDP Configuration
    # ========================================
    LEO_API_KEY: Optional[str] = Field(
        default=None,
        description="LEO CDP API key"
    )
    LEO_API_VALUE: Optional[str] = Field(
        default=None,
        description="LEO CDP API value"
    )
    LEO_BASE_URL: Optional[str] = Field(
        default=None,
        description="LEO CDP base URL"
    )

    # ========================================
    # PostgreSQL Configuration
    # ========================================
    PGSQL_DB_HOST: Optional[str] = Field(
        default=None,
        description="PostgreSQL host"
    )
    PGSQL_DB_PORT: Optional[int] = Field(
        default=5432,
        description="PostgreSQL port"
    )
    PGSQL_DB_NAME: Optional[str] = Field(
        default=None,
        description="PostgreSQL database name"
    )
    PGSQL_DB_USER: Optional[str] = Field(
        default=None,
        description="PostgreSQL user"
    )
    PGSQL_DB_PASSWORD: Optional[str] = Field(
        default=None,
        description="PostgreSQL password"
    )

    @property
    def DATABASE_URL(self) -> Optional[str]:
        """Construct PostgreSQL connection string."""
        if all([self.PGSQL_DB_HOST, self.PGSQL_DB_NAME, self.PGSQL_DB_USER, self.PGSQL_DB_PASSWORD]):
            return (
                f"postgresql://{self.PGSQL_DB_USER}:{self.PGSQL_DB_PASSWORD}"
                f"@{self.PGSQL_DB_HOST}:{self.PGSQL_DB_PORT}/{self.PGSQL_DB_NAME}"
            )
        return None

    # ========================================
    # Redis Cache Configuration
    # ========================================
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis host"
    )
    REDIS_PORT: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Redis port"
    )
    REDIS_DB: int = Field(
        default=0,
        ge=0,
        le=15,
        description="Redis database number"
    )
    REDIS_PASSWORD: Optional[str] = Field(
        default=None,
        description="Redis password (if required)"
    )
    REDIS_CACHE_TTL: int = Field(
        default=3600,
        ge=60,
        description="Cache time-to-live in seconds (default: 1 hour)"
    )

    @property
    def REDIS_URL(self) -> str:
        """Construct Redis connection string."""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ========================================
    # OpenTelemetry & Observability
    # ========================================
    PHOENIX_COLLECTOR_ENDPOINT: Optional[str] = Field(
        default="http://localhost:6006/v1/traces",
        description="Phoenix/OpenTelemetry collector endpoint"
    )
    OTEL_SERVICE_NAME: str = Field(
        default="ai-trip-planner-api",
        description="OpenTelemetry service name"
    )
    OTEL_EXPORTER_OTLP_TIMEOUT: int = Field(
        default=10,
        ge=1,
        description="OTLP exporter timeout in seconds"
    )

    # ========================================
    # SSO Configuration (Optional)
    # ========================================
    SSO_PROVIDER: Optional[Literal["GOOGLE", "FACEBOOK", "OAUTH", "GITHUB"]] = Field(
        default=None,
        description="Single Sign-On provider"
    )
    GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="Google OAuth client ID"
    )
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="Google OAuth client secret"
    )
    FACEBOOK_APP_ID: Optional[str] = Field(
        default=None,
        description="Facebook app ID"
    )
    FACEBOOK_APP_SECRET: Optional[str] = Field(
        default=None,
        description="Facebook app secret"
    )
    GITHUB_CLIENT_ID: Optional[str] = Field(
        default=None,
        description="GitHub OAuth client ID"
    )
    GITHUB_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        description="GitHub OAuth client secret"
    )

    # ========================================
    # CORS Configuration
    # ========================================
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods"
    )
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"],
        description="Allowed headers"
    )

    # ========================================
    # Logging Configuration
    # ========================================
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Application logging level"
    )
    LOG_FILE: Optional[str] = Field(
        default="logs/app.log",
        description="Path to log file"
    )

    # ========================================
    # Data & Report Configuration
    # ========================================
    PERSONA_DATA_DIR: str = Field(
        default="data/personas",
        description="Directory for persona data files"
    )
    REPORTS_DATA_DIR: str = Field(
        default="data/reports",
        description="Directory for generated reports"
    )
    TEMPLATES_DIR: str = Field(
        default="data/templates",
        description="Directory for report templates"
    )
    MAX_REPORT_SIZE_MB: int = Field(
        default=10,
        ge=1,
        description="Maximum report size in MB"
    )

    # ========================================
    # Validators
    # ========================================

    @validator("JWT_SECRET")
    def validate_jwt_secret(cls, v: str) -> str:
        """Ensure JWT secret is not the default in production."""
        if v == "super-secret-key-change-this" and os.getenv("ENVIRONMENT") == "production":
            raise ValueError(
                "❌ JWT_SECRET must be changed in production environment")
        if len(v) < 32:
            raise ValueError(
                "❌ JWT_SECRET must be at least 32 characters long")
        return v

    @validator("OPENAI_API_KEY", "GOOGLE_GEMINI_API_KEY", pre=True, always=True)
    def validate_llm_keys(cls, v: Optional[str], values: dict) -> Optional[str]:
        """Ensure required LLM API keys are set."""
        provider = values.get("LLM_PROVIDER")
        if provider == "OPENAI" and not v and not os.getenv("OPENAI_API_KEY"):
            raise ValueError(
                "❌ OPENAI_API_KEY is required when LLM_PROVIDER=OPENAI")
        if provider == "GOOGLE_GEMINI" and not v and not os.getenv("GOOGLE_GEMINI_API_KEY"):
            raise ValueError(
                "❌ GOOGLE_GEMINI_API_KEY is required when LLM_PROVIDER=GOOGLE_GEMINI")
        return v

    @validator("FRONTEND_DIR")
    def validate_frontend_dir(cls, v: str) -> str:
        """Ensure frontend directory exists."""
        if not os.path.exists(v):
            raise ValueError(f"❌ FRONTEND_DIR does not exist: {v}")
        return v

    # ========================================
    # Configuration Classes
    # ========================================

    class Config:
        """Pydantic configuration for settings."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"  # Allow extra fields from .env

    # ========================================
    # Computed Properties
    # ========================================

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == "development"

    @property
    def api_url_prefix(self) -> str:
        """Get full API URL prefix."""
        return f"{self.API_PREFIX}/{self.API_VERSION}"

    @property
    def llm_config(self) -> dict:
        """Get LLM configuration as dictionary."""
        return {
            "provider": self.LLM_PROVIDER,
            "model": self.LLM_MODEL_NAME,
            "temperature": self.LLM_TEMPERATURE,
            "max_tokens": self.LLM_MAX_TOKENS,
            "timeout": self.LLM_REQUEST_TIMEOUT,
        }

    @property
    def cache_config(self) -> dict:
        """Get cache configuration as dictionary."""
        return {
            "enabled": self.ENABLE_CACHING,
            "redis_url": self.REDIS_URL,
            "ttl": self.REDIS_CACHE_TTL,
        }

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
# Singleton Configuration Instance
# ========================================
@lru_cache()
def get_settings() -> Settings:
    """
    Get or create the settings singleton.
    Uses @lru_cache to ensure only one instance is created.

    Usage in FastAPI:
        from core.config import get_settings
        settings = get_settings()
    """
    return Settings()


# ========================================
# Export
# ========================================
settings = get_settings()
