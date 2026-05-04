from core_llm.meta_llm import MetaLLM
from services.knowledge_service import KnowledgeGraphService
from langchain_core.messages import SystemMessage, HumanMessage

DEFAULT_BUDGET_LEVEL = "mid-range"
DEFAULT_TEMPERATURE = 0.2
COMPUTE_EMBEDDINGS = True  # Set to False to skip embedding and vector search, and always fallback to web search (for testing)

# This file defines the TravelRAGService class, 
# which implements a Retrieval-Augmented Generation (RAG) layer for travel information. 
# It first tries to fetch relevant information from the knowledge graph, and if not found, it falls back to a web search. 
# The retrieved information is then synthesized using an LLM and stored back into the knowledge graph for future queries.
class TravelRAGService:
    """
    RAG Layer:
    - Try Knowledge Graph (vector DB)
    - Fallback to web search
    - Store back into KG (self-improving)
    """

    def __init__(self, kg: KnowledgeGraphService, web_search_fn):
        self.kg = kg
        self.web_search = web_search_fn
        self.llm = MetaLLM.get_llm(temperature=DEFAULT_TEMPERATURE)

    def _synthesize(self, query: str, context: str) -> str:
        """
        Sync LLM call (OK to keep sync)
        """
        res = self.llm.invoke([
            SystemMessage(content="You are a precise travel expert."),
            HumanMessage(content=f"Query: {query}\n\nContext:\n{context}")
        ])
        return res.content

    # ============================================================
    # PUBLIC APIs (ASYNC)
    # ============================================================

    async def get_destination_info(self, destination: str) -> str:
        """
        Get travel info for a destination,  <br>
        using RAG to first check the knowledge graph and then fallback to web search if not found.
         <br>
        Flow:
        1. Try vector search
        2. If found → synthesize
        3. Else → web fallback + store
        """

        results = await self.kg.search(
            query=f"{destination} travel guide",
            keyword=destination,
            category="info"
        )

        if results:
            context = "\n".join([r["content"] for r in results])
            return self._synthesize(destination, context)

        # fallback
        web = self.web_search(
            f"{destination} travel info",
            f"Summarize travel essentials for {destination}"
        )

        content = web["content"]

        # store back → improves future queries
        await self.kg.upsert_knowledge(
            keyword=destination,
            category="info",
            content=content,
            source="web",
            compute_embedding=COMPUTE_EMBEDDINGS
        )

        return content

    async def get_costs(self, destination: str, budget_level: str = DEFAULT_BUDGET_LEVEL) -> str:
        """Get average costs for food, transport, and lodging for a destination and budget level, <br>
        using RAG to check the knowledge graph first and then fallback to web search if not found.

        Args:
            destination (str): the travel destination to query costs for
            budget_level (str, optional): the budget level to query costs for. Defaults to DEFAULT_BUDGET_LEVEL.

        Returns:
            str: the synthesized cost information for the destination and budget level.
         <br>
        Flow:
        1. Try vector search with query "{destination} cost {budget_level}"
        2. If found → synthesize and return
        3. Else → web fallback with query "{destination} travel costs {budget_level}" <br>
           and prompt "Estimate costs for {budget_level} travel in {destination}"
        4. Store the web result back into the knowledge graph with category "cost" and metadata for budget level, to improve future queries.
        5. Return the web result content.
         <br>
        """
        query = f"{destination} cost {budget_level}"

        results = await self.kg.search(
            query=query,
            keyword=destination,
            category="cost"
        )

        if results:
            context = "\n".join([r["content"] for r in results])
            return self._synthesize(query, context)

        web = self.web_search(
            f"{destination} travel costs {budget_level}",
            f"Estimate costs for {budget_level} travel in {destination}"
        )

        content = web["content"]

        await self.kg.upsert_knowledge(
            keyword=destination,
            category="cost",
            content=content,
            source="web",
            metadata={"budget": budget_level},
            compute_embedding=COMPUTE_EMBEDDINGS
        )

        return content