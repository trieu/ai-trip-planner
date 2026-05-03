from __future__ import annotations

import uuid
import logging
from datetime import datetime
from urllib.parse import quote_plus

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import text, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

from arango import ArangoClient

from config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------

# cache settings instance (avoid reloading env repeatedly)
_settings = Settings()

def get_default_tenant_id():
    """
    Python-side fallback ONLY.
    DB is the source of truth for partitioning.
    """
    return _settings.DEFAULT_TENANT_ID


# ---------------------------------------------------------------------
# Base & Mixins
# ---------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 style Declarative Base."""
    pass


class TimestampMixin:
    """
    Standardized auditing timestamps.
    Uses DB-side defaults for consistency across services.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False
    )


# ---------------------------------------------------------------------
# Database Settings
# ---------------------------------------------------------------------

class DatabaseSettings(BaseSettings):
    """
    Centralized database configuration.

    Priority:
    1. OS environment variables
    2. .env file
    3. Default values
    """

    # -------------------------
    # PostgreSQL (Target)
    # -------------------------
    PGSQL_DB_HOST: str = Field(default="localhost")
    PGSQL_DB_PORT: int = Field(default=5432)
    PGSQL_DB_NAME: str = Field(default="leo_cdp")
    PGSQL_DB_USER: str = Field(default="postgres")
    PGSQL_DB_PASSWORD: str

    # -------------------------
    # ArangoDB (Source)
    # -------------------------
    ARANGO_HOST: str = Field(default="http://localhost:8529")
    ARANGO_DB: str = Field(default="leo_cdp_source")
    ARANGO_USER: str = Field(default="root")
    ARANGO_PASSWORD: str

    # ✅ Pydantic v2 config
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # -----------------------------------------------------------------
    # PostgreSQL
    # -----------------------------------------------------------------

    @property
    def pg_dsn(self) -> str:
        """
        Build PostgreSQL DSN (psycopg).

        - Escapes password safely
        - Injects AGE search_path
        """

        encoded_password = quote_plus(self.PGSQL_DB_PASSWORD)

        return (
            f"postgresql://{self.PGSQL_DB_USER}:{encoded_password}@"
            f"{self.PGSQL_DB_HOST}:{self.PGSQL_DB_PORT}/"
            f"{self.PGSQL_DB_NAME}"
            f"?options=-c%20search_path%3Dag_catalog,public"
        )

    @property
    def pg_async_dsn(self) -> str:
        """
        DSN for SQLAlchemy async engine (asyncpg).
        """
        encoded_password = quote_plus(self.PGSQL_DB_PASSWORD)

        return (
            f"postgresql+asyncpg://{self.PGSQL_DB_USER}:{encoded_password}@"
            f"{self.PGSQL_DB_HOST}:{self.PGSQL_DB_PORT}/"
            f"{self.PGSQL_DB_NAME}"
        )

    def get_pg_connection(self) -> psycopg.Connection:
        """
        Create a synchronous PostgreSQL connection.
        Used for lightweight queries or scripts.
        """
        return psycopg.connect(
            self.pg_dsn,
            row_factory=dict_row,
        )

    # -----------------------------------------------------------------
    # ArangoDB
    # -----------------------------------------------------------------

    def get_arango_db(self):
        """
        Create ArangoDB database connection.
        """

        client = ArangoClient(hosts=self.ARANGO_HOST)

        db = client.db(
            self.ARANGO_DB,
            username=self.ARANGO_USER,
            password=self.ARANGO_PASSWORD,
        )

        # safer logging instead of print
        logger.info(f"Connected to ArangoDB database: {db.name}")

        if db.name != self.ARANGO_DB:
            logger.warning(
                f"Expected DB '{self.ARANGO_DB}', but got '{db.name}'"
            )

        return db