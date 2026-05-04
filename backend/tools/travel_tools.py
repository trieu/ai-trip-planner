import logging

from langchain_core.tools import tool

from services.knowledge_service import KnowledgeGraphService
from services.travel_rag_service import TravelRAGService
from tools.web_search import search_or_fallback
from config import Settings

logger = logging.getLogger(__name__)

# ================================
# Init services (singleton style)
# ================================

# Initialize the knowledge graph service and RAG service once, to be reused across tool calls.
kg_service = KnowledgeGraphService(Settings().PGSQL_DATABASE_DSN)

# The RAG service is initialized with the knowledge graph service and a search fallback function.
rag = TravelRAGService(kg_service, search_or_fallback)

# ================================
#  Tools for travel planning, using RAG to fetch information from the knowledge graph and web search as needed.
# ================================

@tool
async def get_destination_info(destination: str) -> str:
    """Get information for a destination using RAG."""
    logger.info(f"[TOOL] destination info: {destination}")
    return await rag.get_destination_info(destination)


@tool
async def get_costs(destination: str, budget_level: str) -> str:
    """Get average costs for food, transport, and lodging using RAG."""
    logger.info(f"[TOOL] cost: {destination} | {budget_level}")
    return await rag.get_costs(destination, budget_level)