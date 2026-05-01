# services/knowledge_service.py

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import logging
from typing import List, Dict, Any

from sqlalchemy import select

from services.pgsql_service import build_pg_dsn
from services.data_models.travel_knowledge import TravelKnowledge
from meta_llm import MetaLLM

logger = logging.getLogger(__name__)

# This file defines the KnowledgeGraphService class,
# which provides methods to upsert knowledge and perform vector search on the travel knowledge graph.

class KnowledgeGraphService:
    """ Knowledge Graph Service using PostgreSQL with pgvector for travel information.
    - upsert_knowledge: to insert or update knowledge entries with embeddings.
    - search: to perform vector search based on a query and optional filters like destination and category
    """

    def __init__(self, database_url: str = None):
        self.embedder = MetaLLM.get_embeddings()
        self.DATABASE_URL = database_url or build_pg_dsn()  # keep your asyncpg DSN

        self.engine = create_async_engine(
            self.DATABASE_URL,
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
    # UPSERT KNOWLEDGE INTO THE GRAPH
    # ============================================================
    async def upsert_knowledge(
        self,
        destination: str,
        category: str,
        content: str,
        source: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        emb = self._embed(content)

        async with self.AsyncSessionLocal() as session:
            try:
                obj = TravelKnowledge(
                    destination=destination,
                    category=category,
                    content=content,
                    source=source,
                    embedding=emb,  # ✅ no conversion needed
                    metadata=metadata or {}
                )

                session.add(obj)
                await session.commit()

            except Exception as e:
                logger.error(f"[UPSERT ERROR] {e}")
                await session.rollback()

    # ============================================================
    # VECTOR SEARCH IN THE KNOWLEDGE GRAPH
    # ============================================================
    async def search(
        self,
        query: str,
        destination: str = None,
        category: str = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:

        emb = self._embed(query)

        async with self.AsyncSessionLocal() as session:
            try:
                stmt = select(TravelKnowledge)

                if destination:
                    stmt = stmt.where(TravelKnowledge.destination == destination)

                if category:
                    stmt = stmt.where(TravelKnowledge.category == category)

                # 🔥 pgvector native operator
                stmt = stmt.order_by(
                    TravelKnowledge.embedding.cosine_distance(emb)
                ).limit(top_k)

                result = await session.execute(stmt)
                rows = result.scalars().all()

                return [
                    {
                        "content": r.content,
                        "source": r.source,
                        "metadata": r.metadata
                    }
                    for r in rows
                ]

            except Exception as e:
                logger.error(f"[SEARCH ERROR] {e}")
                return []
