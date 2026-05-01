import logging
import json
from typing import Any, Dict, List

from tavily import TavilyClient
from langchain_core.messages import SystemMessage, HumanMessage

from meta_llm import MetaLLM
from tools.cache_utils import get_cache, set_cache
from tools.text_utils import normalize_text
from config import Settings


# ============================================================
# Logging
# ============================================================
logger = logging.getLogger("agentic_tools.web_search")


# ============================================================
# Constants
# ============================================================
MAX_SEARCH_RESULTS = 6
TOP_K_RESULTS = 3
LLM_TEMPERATURE = 0.2
SEARCH_PREFIX = "search:v2"


# ============================================================
# Helpers
# ============================================================

def _search_cache_key(query: str) -> str:
    return f"{SEARCH_PREFIX}:{normalize_text(query)}"


def _enrich_query(query: str) -> str:
    """
    Expand query to improve recall + relevance.
    """
    return f"{query} travel guide highlights cost tips best places"


def _score_result(result: Dict[str, Any], query: str) -> float:
    """
    Simple heuristic scoring:
    - keyword overlap
    - content length
    - URL credibility hint
    """
    content = (result.get("content") or "").lower()

    if not content:
        return 0.0

    score = 0.0

    # keyword overlap
    for token in query.lower().split():
        if token in content:
            score += 1.0

    # length bonus (avoid thin pages)
    score += min(len(content) / 500, 2.0)

    # prefer known domains (optional heuristic)
    url = result.get("url", "")
    if any(x in url for x in ["wikipedia", "lonelyplanet", "tripadvisor"]):
        score += 1.5

    return score


def _select_best_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Rank and select top results.
    """
    scored = [(r, _score_result(r, query)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [r for r, _ in scored[:TOP_K_RESULTS]]


def _merge_contents(results: List[Dict[str, Any]]) -> str:
    """
    Merge multiple sources into a single coherent context.
    """
    contents = []
    for r in results:
        c = r.get("content", "").strip()
        if c:
            contents.append(c)

    return "\n\n".join(contents[:3])


def _llm_summarize(context: str, query: str) -> str:
    """
    Use LLM to refine aggregated search results.
    """
    llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)

    res = llm.invoke([
        SystemMessage(
            content="You are a precise travel researcher. Extract only useful, factual, non-generic insights."
        ),
        HumanMessage(
            content=f"Query: {query}\n\nContext:\n{context}\n\nSummarize clearly."
        )
    ])

    return str(res.content).strip()


# ============================================================
# Main Function
# ============================================================

def search_or_fallback(query: str, fallback_instruction: str) -> Dict[str, Any]:
    """
    Improved search pipeline:
    - Cache
    - Query enrichment
    - Multi-result ranking
    - LLM summarization
    - Fallback
    """

    if not query:
        return {"content": "", "images": []}

    cache_key = _search_cache_key(query)

    # =========================
    # 1. Cache
    # =========================
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[CACHE HIT] {query}")
        try:
            return json.loads(cached)
        except Exception:
            pass

    # =========================
    # 2. Tavily Search
    # =========================
    api_key = Settings().TAVILY_API_KEY

    if api_key:
        try:
            tavily = TavilyClient(api_key)

            enriched_query = _enrich_query(query)

            logger.info(f"[SEARCH] {enriched_query}")

            data = tavily.search(
                enriched_query,
                max_results=MAX_SEARCH_RESULTS,
                search_depth="advanced",
                include_images=True
            )

            results = data.get("results", [])
            images = data.get("images", [])[:3]

            if results:
                # ✅ rank + select
                top_results = _select_best_results(results, query)

                # ✅ merge
                merged_content = _merge_contents(top_results)

                # ✅ summarize (key improvement)
                refined = _llm_summarize(merged_content, query)

                payload = {
                    "content": refined,
                    "images": images,
                    "sources": [r.get("url") for r in top_results]
                }

                set_cache(cache_key, json.dumps(payload, default=str))

                return payload

        except Exception as e:
            logger.warning(f"[SEARCH FAILED] {e}")

    else:
        logger.info("TAVILY_API_KEY not set")

    # =========================
    # 3. LLM Fallback
    # =========================
    try:
        logger.info(f"[FALLBACK] {query}")

        llm = MetaLLM.get_llm(temperature=LLM_TEMPERATURE)

        res = llm.invoke([
            SystemMessage(content="Provide accurate and concise travel insights."),
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
        logger.error(f"[FALLBACK FAILED] {e}")
        return {"content": "", "images": []}