import logging

import httpx
from meta_llm import MetaLLM
import os
from langchain_core.messages import SystemMessage, HumanMessage
from tools.cache_utils import get_cache, set_cache
from tools.text_utils import normalize_text


# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("agentic_tools.web_search")

# ============================================================
MAX_SEARCH_RESULTS = 2
SEARCH_TIMEOUT_SECONDS = 10.0
LLM_TEMPERATURE = 0.3
SEARCH_PREFIX = "search"
# ============================================================


def _search_cache_key(query: str) -> str:
    return f"{SEARCH_PREFIX}:{normalize_text(query)}"


def _search_or_fallback(query: str, fallback_instruction: str) -> str:
    """
    Web search with Redis cache + LLM fallback.
    """

    if not query:
        return ""

    cache_key = _search_cache_key(query)

    # =========================
    # 1. Cache lookup
    # =========================
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[CACHE HIT] search: {query}")
        return cached

    tavily_key = os.getenv("TAVILY_API_KEY")

    # =========================
    # 2. Try Tavily search
    # =========================
    if tavily_key:
        try:
            logger.info(f"[SEARCH] Tavily query: {query}")

            with httpx.Client(timeout=SEARCH_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": MAX_SEARCH_RESULTS,
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                result = None

                if data.get("answer"):
                    result = data["answer"]
                elif data.get("results"):
                    result = data["results"][0].get("content", "")

                if result:
                    # =========================
                    # Cache success result
                    # =========================
                    set_cache(cache_key, result)
                    return result

        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    # =========================
    # 3. Fallback to LLM
    # =========================
    try:
        logger.info(f"[FALLBACK] LLM for query: {query}")

        llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)

        res = llm.invoke([
            SystemMessage(content="Provide a concise travel guide."),
            HumanMessage(content=fallback_instruction)
        ])

        result = str(res.content).strip()

        if result:
            set_cache(cache_key, result)

        return result

    except Exception as e:
        logger.error(f"LLM fallback failed: {e}")
        return ""
