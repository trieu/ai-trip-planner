from __future__ import annotations

import uuid
from sqlalchemy import text, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from urllib.parse import quote_plus
import psycopg
from pydantic import Field
from pydantic_settings import BaseSettings
from psycopg.rows import dict_row
from arango import ArangoClient

from config import Settings

# ---------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------
def get_default_tenant_id():
    """
    Python-side fallback ONLY.
    DB is the source of truth for partitioning.
    """
    return Settings().DEFAULT_TENANT_ID

# ---------------------------------------------------------------------
# Base & Mixins
# ---------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 style Declarative Base."""
    pass


class TimestampMixin:
    """Standardized auditing timestamps for high-scale tracking."""
    created_at: Mapped[uuid.UUID] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()")
    )
    updated_at: Mapped[uuid.UUID] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()")
    )

# ---------------------------------------------------------------------
# Database Settings
# ---------------------------------------------------------------------

class DatabaseSettings(BaseSettings):
    """
    Database connection settings for PostgreSQL and ArangoDB.
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

    class Config:
        # Pydantic automatically handles the priority:
        # 1. OS Environment Variables (Highest Priority - Docker overrides this)
        # 2. .env file values
        # 3. Default values (Lowest Priority)

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignores other extra fields

    @property
    def pg_dsn(self) -> str:
        """
        Constructs a safe PostgreSQL connection string (DSN).
        Handles special characters in the password and includes the port.

        Updates:
        - Appends '?options=-c search_path=ag_catalog,public' 
          to ensure Apache AGE functions are loaded and prioritized.
        """
        # Safely encode the password to handle characters like '@', '/', ':'
        encoded_password = quote_plus(self.PGSQL_DB_PASSWORD)

        # We pass 'options' to set the search_path at connection time.
        # This is strictly required for AGE to recognize graph syntax in SQL.
        return (
            f"postgresql://{self.PGSQL_DB_USER}:{encoded_password}@"
            f"{self.PGSQL_DB_HOST}:{self.PGSQL_DB_PORT}/"
            f"{self.PGSQL_DB_NAME}?options=-c%20search_path%3Dag_catalog,public"
        )

    def get_arango_db(self):
        """
        Create and return an ArangoDB database connection.
        """

        client = ArangoClient(hosts=self.ARANGO_HOST)

        db = client.db(
            self.ARANGO_DB,
            username=self.ARANGO_USER,
            password=self.ARANGO_PASSWORD,
        )

        # Optional but useful sanity check
        print(f"🔌 Connected to ArangoDB database: {db.name}")

        if db.name != self.ARANGO_DB:
            print(
                f"⚠️ WARNING: Expected '{self.ARANGO_DB}', "
                f"but connected to '{db.name}'"
            )

        return db

    def get_pg_connection(self) -> psycopg.Connection:
        """
        Create a PostgreSQL connection using Settings.
        """
        return psycopg.connect(
            self.pg_dsn,
            row_factory=dict_row,
        )



