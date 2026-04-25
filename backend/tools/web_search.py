import logging
from typing import Any, Dict
from meta_llm import MetaLLM
import os
from langchain_core.messages import SystemMessage, HumanMessage
from tools.cache_utils import get_cache, set_cache
from tools.text_utils import normalize_text
import json
from tavily import TavilyClient


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


def _search_or_fallback(query: str, fallback_instruction: str) -> Dict[str, Any]:
    """
    Web search with:
    - Redis cache (JSON)
    - Tavily structured result (content + images)
    - LLM fallback
    """

    if not query:
        return {"content": "", "images": []}

    cache_key = _search_cache_key(query)

    # =========================
    # 1. Cache lookup
    # =========================
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[CACHE HIT] {query}")
        try:
            return json.loads(cached)
        except Exception:
            pass  # corrupted cache fallback

    # =========================
    # 2. Tavily search
    # =========================
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    tavily_client = TavilyClient(TAVILY_API_KEY)
    
    if TAVILY_API_KEY:
        try:
            logger.info(f"[SEARCH] Tavily: {query}")

            data = tavily_client.search(
                query,
                max_results=MAX_SEARCH_RESULTS,
                search_depth="advanced",
                include_images=True
            )

            # Tavily returns dict, not list
            results = data.get("results", [])
            images = data.get("images", [])

            if results:
                best = results[0]

                payload = {
                    "content": best.get("content", ""),
                    "images": images[:3],  # limit images
                    "source": best.get("url")
                }

                # ✅ cache as JSON string
                set_cache(cache_key, json.dumps(payload, default=str))

                return payload

        except Exception as e:
            logger.warning(f"Tavily failed: {e}")

    # =========================
    # 3. LLM fallback
    # =========================
    try:
        logger.info(f"[FALLBACK] LLM: {query}")

        llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)

        res = llm.invoke([
            SystemMessage(content="Provide a concise travel guide."),
            HumanMessage(content=fallback_instruction)
        ])

        payload = {
            "content": str(res.content).strip(),
            "images": [],
            "source": "llm"
        }

        set_cache(cache_key, json.dumps(payload, default=str))

        return payload

    except Exception as e:
        logger.error(f"LLM fallback failed: {e}")
        return {"content": "", "images": []}
