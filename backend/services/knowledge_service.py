# services/knowledge_service.py

import uuid
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, update, func


from services.data_models.dbo_knowledge_base import KnowledgeBase
from core_llm.meta_llm import MetaLLM

logger = logging.getLogger(__name__)

class KnowledgeGraphService:
    """
    Knowledge Graph Service (PostgreSQL + pgvector) <br>
    The base knowledge repository for storing and retrieving AI-enriched content. <br>
    Before using, ensure you have the corresponding PostgreSQL table created with the correct schema and pgvector extension enabled. <br>
    Key features:
    - Vector embeddings for semantic search (using MetaLLM)
    - Metadata storage for flexible filtering
    - Upsert logic to avoid duplicates based on content hash

    Key behavior:
    - tenant_id is OPTIONAL → falls back to model default
    - Proper UPSERT using (tenant_id, category, content_hash)
    """

    def __init__(self, database_dns: Optional[str] = None):
        self.embedder = MetaLLM.get_embeddings()
        self.PGSQL_DATABASE_DSN = database_dns or None 
        
        if self.PGSQL_DATABASE_DSN is None:
            raise ValueError("PGSQL_DATABASE_DSN must be provided either directly or via config.build_pg_dsn()")

        self.engine = create_async_engine(
            self.PGSQL_DATABASE_DSN,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )

        self.AsyncSessionLocal = async_sessionmaker(
            self.engine,
            expire_on_commit=False
        )

    # ============================================================
    # Embedding
    # ============================================================
    def _embed(self, text: str) -> List[float]:
        return self.embedder.embed_query(text)

    # ============================================================
    # UPSERT
    # ============================================================
    async def upsert_knowledge(
        self,
        keyword: str,
        category: str,
        content: str,
        source: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
        compute_embedding: bool = False,
        tenant_id: Optional[uuid.UUID] = None,  # ✅ last param
    ) -> Optional[uuid.UUID]:

        emb = self._embed(content) if compute_embedding else None

        values = dict(
            id=uuid.uuid4(),
            keyword=keyword,
            category=category,
            content=content,
            source=source,
            embedding=emb,
            metadata_serialized=metadata or {},
        )

        # ✅ Only include tenant_id if explicitly provided
        if tenant_id is not None:
            values["tenant_id"] = tenant_id

        async with self.AsyncSessionLocal() as session: 
            try:
                stmt = insert(KnowledgeBase).values(**values)

                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        KnowledgeBase.tenant_id,
                        KnowledgeBase.category,
                        KnowledgeBase.content_hash,
                    ],
                    set_={
                        "content": stmt.excluded.content,
                        "keyword": stmt.excluded.keyword,
                        "metadata": stmt.excluded.metadata,
                        "source": stmt.excluded.source,
                        "embedding": stmt.excluded.embedding,
                        "updated_at": func.now(),
                        "is_active": True,
                    },
                ).returning(KnowledgeBase.id)

                result = await session.execute(stmt)
                await session.commit()

                return result.scalar_one()

            except Exception:
                logger.exception("[UPSERT ERROR]")
                await session.rollback()
                return None

    # ============================================================
    # BULK UPSERT
    # ============================================================
    async def bulk_upsert(
        self,
        rows: List[Dict[str, Any]],
        tenant_id: Optional[uuid.UUID] = None,  # ✅ last param
    ):
        if not rows:
            return

        prepared = []
        for r in rows:
            row = dict(r)

            row["id"] = uuid.uuid4()
            row["metadata_serialized"] = row.pop("metadata", {})

            if tenant_id is not None:
                row["tenant_id"] = tenant_id

            prepared.append(row)

        async with self.AsyncSessionLocal() as session:
            try:
                stmt = insert(KnowledgeBase).values(prepared)

                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        KnowledgeBase.tenant_id,
                        KnowledgeBase.category,
                        KnowledgeBase.content_hash,
                    ],
                    set_={
                        "content": stmt.excluded.content,
                        "keyword": stmt.excluded.keyword,
                        "metadata": stmt.excluded.metadata,
                        "source": stmt.excluded.source,
                        "embedding": stmt.excluded.embedding,
                        "updated_at": func.now(),
                        "is_active": True,
                    },
                )

                await session.execute(stmt)
                await session.commit()

            except Exception:
                logger.exception("[BULK UPSERT ERROR]")
                await session.rollback()

    # ============================================================
    # SEARCH
    # ============================================================
    async def search(
        self,
        query: str,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        top_k: int = 3,
        tenant_id: Optional[uuid.UUID] = None,  # ✅ last param
    ) -> List[Dict[str, Any]]:

        emb = self._embed(query)

        async with self.AsyncSessionLocal() as session:
            try:
                stmt = select(KnowledgeBase).where(
                    KnowledgeBase.is_active.is_(True)
                )

                # ✅ Only filter tenant if provided
                if tenant_id is not None:
                    stmt = stmt.where(KnowledgeBase.tenant_id == tenant_id)

                if keyword:
                    stmt = stmt.where(KnowledgeBase.keyword == keyword)

                if category:
                    stmt = stmt.where(KnowledgeBase.category == category)

                stmt = stmt.order_by(
                    KnowledgeBase.embedding.cosine_distance(emb)
                ).limit(top_k)

                result = await session.execute(stmt)
                rows = result.scalars().all()

                return [
                    {
                        "id": r.id,
                        "content": r.content,
                        "source": r.source,
                        "metadata": r.metadata_serialized,
                    }
                    for r in rows
                ]

            except Exception:
                logger.exception("[SEARCH ERROR]")
                return []