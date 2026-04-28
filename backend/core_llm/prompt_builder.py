from typing import Any, Dict

from core_llm.state_models import TripState
from tools.text_utils import merge_unique_csv

DEFAULT_BUDGET_LEVEL = "moderate"
DEFAULT_LANGUAGE = "English"


def build_trip_planner_prompt(state: TripState) -> str:
    """
    Backward-compatible prompt builder.
    - Returns STRING (fixes your crash)
    - Works for both OpenAI + Gemini
    - Strong language enforcement
    """

    req = state.get("trip_request", {}) or {}
    user_profile = state.get("user_profile", {}) or {}

    # =========================
    # Normalize inputs
    # =========================
    destination = req.get("destination") or "Unknown destination"
    duration = req.get("duration") or "Unknown duration"
    budget = req.get("budget") or DEFAULT_BUDGET_LEVEL

    user_interests = merge_unique_csv(
        user_profile,
        "current_interests",
        "personal_interests"
    ) or "General travel"

    user_language = user_profile.get("language") or DEFAULT_LANGUAGE

    weather = state.get("weather") or "Not available"
    cost_data = state.get("budget") or "Not available"
    research_data = state.get("research") or "Not available"

    # =========================
    # SINGLE STRING PROMPT (IMPORTANT)
    # =========================
    prompt = f"""
You are a professional travel planner AI.

CRITICAL:
- Output MUST be 100% in {user_language}
- NEVER mix languages
- Translate all input data into {user_language}

FORMAT:
- ONLY use: <h1>, <h2>, <ul>, <li>, <p>, <strong>, <b>, and plain text
- NO markdown
- NO explanations
- NO questions

# INPUT DATA
Destination: {destination}
Duration: {duration}
Budget: {budget}
Interests: {user_interests}
Weather: {weather}

COST DATA:
{cost_data}

LOCAL RESEARCH:
{research_data}

# REQUIREMENTS
- Use real places from research
- Include food + transport daily
- Budget logic:
  - Budget → street food
  - Luxury → premium services

# STRUCTURE

<h1>Quick Summary</h1>
<ul>
<li><strong>Destination:</strong> ...</li>
<li><strong>Trip Snapshot:</strong> ...</li>
<li><strong>Budget:</strong> ...</li>
<li><strong>Interests:</strong> ...</li>
<li><strong>Weather:</strong> ...</li>
<li><strong>Top Experiences:</strong>
<ul><li>...</li></ul>
</li>
<li><strong>Where to Stay:</strong>
<ul><li>...</li></ul>
</li>
</ul>

<h1>Day 1: ...</h1>
<h2>Morning</h2>
<ul>
<li><strong>Activity</strong>: description</li>
</ul>

# HARD RULE
Everything MUST be in {user_language}.
If not → regenerate internally.
""".strip()

    return prompt