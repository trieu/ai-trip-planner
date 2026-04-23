from langchain_core.tools import tool
from tools.web_search import _search_or_fallback

# ================================
# Tools & Helpers
# ================================


@tool
def get_destination_info(destination: str) -> str:
    """Get information for a destination."""
    # TODO cache results in real system to avoid repeated searches for same destination
    return _search_or_fallback(
        f"{destination} travel info",
        f"Summarize travel essentials for {destination}."
    )


@tool
def get_costs(destination: str, budget_level: str) -> str:
    """Get average costs for food, transport, and lodging."""
    # TODO cache results in real system to avoid repeated searches for same destination and budget level
    return _search_or_fallback(
        f"{destination} travel costs {budget_level}",
        f"Estimated costs for {budget_level} travel in {destination}."
    )
