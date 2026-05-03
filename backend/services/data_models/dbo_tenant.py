from __future__ import annotations

import logging
import uuid
from typing import Any, Final, Optional

from sqlalchemy import String, UniqueConstraint, select, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from services.data_models.dbo_base import Base, TimestampMixin

# ---------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------

logger = logging.getLogger(__name__)

DEFAULT_TENANT_NAME: Final[str] = "master"
TENANT_STATUS_ACTIVE: Final[str] = "active"

# ---------------------------------------------------------------------
# ORM Model: Tenant
# ---------------------------------------------------------------------

class Tenant(Base, TimestampMixin):
    """
    Tenant represents an isolated logical customer boundary.
    Acts as the anchor for partitioning and RLS in the LEO CDP ecosystem.
    """
    __tablename__ = "tenant"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    tenant_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        server_default=text(f"'{DEFAULT_TENANT_NAME}'"),
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text(f"'{TENANT_STATUS_ACTIVE}'"),
    )

    # Keycloak integration
    keycloak_realm: Mapped[str] = mapped_column(String(255), nullable=False)
    keycloak_client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    keycloak_org_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Extensible metadata for marketing/financial config
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "keycloak_realm",
            "tenant_name",
            name="uq_tenant_keycloak_realm",
        ),
    )

    def __repr__(self) -> str:
        return f"<Tenant(name='{self.tenant_name}', id={self.tenant_id})>"


# ---------------------------------------------------------------------
# Context Resolver & RLS Support
# ---------------------------------------------------------------------

def resolve_tenant_id(session: Session, tenant_name: str = DEFAULT_TENANT_NAME) -> uuid.UUID:
    """
    Resolves tenant_id with SQLAlchemy 2.0 scalar_one() for strictness.
    """
    stmt = select(Tenant.tenant_id).where(Tenant.tenant_name == tenant_name)
    tenant_id = session.execute(stmt).scalar_one_or_none()

    if not tenant_id:
        raise RuntimeError(f"Tenant context error: '{tenant_name}' not found.")
    
    return tenant_id


def set_tenant_context(session: Session, tenant_id: uuid.UUID) -> None:
    """
    Enforces Row Level Security (RLS) and helps the query planner 
    route to the correct partitions in PostgreSQL 16.
    """
    # Use bindparam for safety and performance
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    logger.debug("SQL Context bound to tenant_id: %s", tenant_id)


def prepare_tenant_session(session: Session, tenant_name: str = DEFAULT_TENANT_NAME) -> uuid.UUID:
    """
    Initializes the session for the given tenant. 
    Crucial for RAG knowledge_base queries at 999M row scale.
    """
    tenant_id = resolve_tenant_id(session, tenant_name)
    set_tenant_context(session, tenant_id)
    
    logger.info("Session prepared for %s [%s]", tenant_name, tenant_id)
    return tenant_id