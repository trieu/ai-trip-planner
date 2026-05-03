import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Text,
    String,
    Boolean,
    TIMESTAMP,
    func,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, BYTEA
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector  # NOTE: still used as logical type

from config import Settings
from services.data_models.dbo_base import Base, get_default_tenant_id


class KnowledgeBase(Base):
    """
    ORM mapping for:

    -- knowledge_base (Partitioned AI-ENABLED CONTENT REPOSITORY)

    IMPORTANT:
    - Table is HASH PARTITIONED in PostgreSQL → ORM does NOT manage partitions
    - Some fields (content_hash, embedding type) are DB-controlled
    """

    __tablename__ = "knowledge_base"

    # ============================================================
    # PRIMARY KEY (MATCHES SQL)
    # PRIMARY KEY (tenant_id, id)
    # ============================================================
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        # fallback only (DB should supply in real flow)
        default=get_default_tenant_id,
        comment="Partition key (HASH). Required for multi-tenant scaling."
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,  # mirrors gen_random_uuid()
        comment="Unique row identifier"
    )

    # ============================================================
    # CONTEXT FIELDS
    # ============================================================
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        server_default=text("'en'"),
        comment="Content language (default: en)"
    )

    domain: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Domain classification (Travel, Finance, etc.)"
    )

    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Category (info, cost, itinerary, etc.)"
    )

    keyword: Mapped[Optional[str]] = mapped_column(
        String(255),
        comment="Keyword for fast lookup"
    )

    # ============================================================
    # CONTENT
    # ============================================================
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw content used for RAG retrieval"
    )

    content_hash: Mapped[Optional[bytes]] = mapped_column(
        BYTEA,
        nullable=True,
        comment="""
        GENERATED ALWAYS (digest(content, 'sha256')) STORED

        IMPORTANT:
        - DO NOT set in application
        - Used for deduplication at billion-row scale
        """
    )

    source: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Origin of the content (API, crawl, user input)"
    )

    # ============================================================
    # METADATA (JSONB)
    # ============================================================
    metadata_serialized: Mapped[Dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="""
        Schema-less attributes (price_range, rating, etc.)
        Indexed via GIN for fast filtering
        """
    )

    # ============================================================
    # VECTOR (pgvector / halfvec)
    # ============================================================
    embedding: Mapped[Optional[Vector]] = mapped_column(
        Vector(1536),
        comment="""
        Logical mapping to halfvec(1536) in DB

        NOTE:
        - DB uses halfvec for storage optimization (16-bit)
        - ORM still uses Vector(1536)
        - Indexed via HNSW (created manually in SQL)
        """
    )

    # ============================================================
    # LIFECYCLE
    # ============================================================
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="Soft delete flag"
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Row creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),  # app-side update; DB trigger is better if strict
        comment="Last update timestamp"
    )

    # ============================================================
    # INDEXES (MATCH SQL EXACTLY)
    # ============================================================
    __table_args__ = (
        # UNIQUE (tenant_id, category, content_hash)
        Index(
            "uniq_kb_tenant_hash",
            "tenant_id",
            "category",
            "content_hash",
            unique=True
        ),

        # WHERE is_active = TRUE
        Index(
            "idx_kb_tenant_domain_lang",
            "tenant_id",
            "domain",
            "language",
            postgresql_where=text("is_active = TRUE")
        ),

        # keyword index
        Index(
            "idx_kb_keyword",
            "tenant_id",
            "keyword"
        ),

        # JSONB GIN index
        Index(
            "idx_kb_metadata_gin",
            metadata_serialized,
            postgresql_using="gin"
        ),

        # Full-text search index
        Index(
            "idx_kb_content_fts",
            text("to_tsvector('simple', content)"),
            postgresql_using="gin"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeBase("
            f"tenant_id={self.tenant_id}, "
            f"id={self.id}, "
            f"domain={self.domain}, "
            f"lang={self.language})>"
        )
