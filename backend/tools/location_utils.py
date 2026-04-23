import logging
import time
from typing import Optional, Dict, Any, List

import requests

from tools.cache_utils import geo_cache_key, get_geo_cache, set_geo_cache
from tools.text_utils import canonicalize_city_name, normalize_text, looks_vietnamese

# Setup logger
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 1. LOCALIZATION DATASET
# -----------------------------------------------------------------------------
# Map of ISO Country Codes -> ISO Language Codes -> Localized Country Name
LOCALIZED_COUNTRY_HINTS = {
    "VN": {
        "vi": "Việt Nam",
        "en": "Vietnam",
        "zh": "越南",
        "ja": "ベトナム",
        "ko": "베트남",
        "fr": "Viêt Nam",
        "th": "เวียดนาม",
    },
    "US": {
        "en": "United States",
        "vi": "Hoa Kỳ",
        "zh": "美国",
        "ja": "アメリカ",
        "es": "Estados Unidos",
    },
    "JP": {
        "ja": "日本",
        "en": "Japan",
        "vi": "Nhật Bản",
        "zh": "日本",
    },
    "FR": {
        "fr": "France",
        "en": "France",
        "vi": "Pháp",
        "de": "Frankreich",
    }
}


# =========================
# Safe HTTP request
# =========================

def _safe_request(url: str, params: dict, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == retries:
                logger.warning(f"Geocoding failed after retries: {e}")
                return None
            time.sleep(0.3 * (attempt + 1))  # backoff


def get_coordinates(city_name: str) -> Optional[Dict[str, Any]]:
    """
    High-accuracy geocoder with:
    - country-aware query shaping
    - hard filtering when confident
    - multi-stage ranking
    """

    # -------------------------
    # 1. Validation
    # -------------------------
    if not city_name or not isinstance(city_name, str):
        logger.warning(f"Invalid city_name: {city_name}")
        return None

    city_name = city_name.strip()
    if len(city_name) < 2:
        return None

    # -------------------------
    # 2. Cache
    # -------------------------
    cache_key = geo_cache_key(city_name)
    cached = get_geo_cache(cache_key)
    if cached:
        return cached

    geo_url = "https://geocoding-api.open-meteo.com/v1/search"

    canonical = canonicalize_city_name(city_name)
    normalized = normalize_text(city_name)

    # -------------------------
    # 3. Detect strong country intent
    # -------------------------
    is_vn = looks_vietnamese(city_name)
    country_bias = "VN" if is_vn else None
    country_hint = LOCALIZED_COUNTRY_HINTS.get("VN", {}) if is_vn else {}

    # -------------------------
    # 4. Build aggressive query set
    # -------------------------
    queries = []

    if country_bias:
        for lang in ["vi", "en"]:
            country_str = country_hint.get(lang, "Vietnam")

            queries.extend([
                (f"{city_name}, {country_str}", lang),
                (f"{canonical}, {country_str}", lang),
            ])

    # fallback queries
    queries.extend([
        (city_name, "vi"),
        (canonical, "vi"),
        (city_name, "en"),
    ])

    # deduplicate
    seen = set()
    queries = [q for q in queries if not (q in seen or seen.add(q))]

    candidates: List[Dict[str, Any]] = []

    # -------------------------
    # 5. Query + collect
    # -------------------------
    for query, lang in queries:
        data = _safe_request(
            geo_url,
            {
                "name": query,
                "count": 5,
                "language": lang,
                "format": "json"
            }
        )

        if not data or not isinstance(data.get("results"), list):
            continue

        for r in data["results"]:
            lat, lon = r.get("latitude"), r.get("longitude")
            if lat is None or lon is None:
                continue

            cc = r.get("country_code")

            # -------------------------
            # 🔥 HARD FILTER (critical)
            # -------------------------
            if country_bias == "VN" and cc != "VN":
                continue

            score = 0

            # strong country match
            if cc == country_bias:
                score += 10

            # name match
            resolved = normalize_text(r.get("name", ""))
            if resolved == canonical:
                score += 5
            elif canonical in resolved:
                score += 3

            # admin match (province / region)
            admin1 = normalize_text(r.get("admin1", "") or "")
            admin2 = normalize_text(r.get("admin2", "") or "")

            if canonical in admin1 or canonical in admin2:
                score += 3

            # population
            pop = r.get("population") or 0
            if pop > 1_000_000:
                score += 2
            elif pop > 100_000:
                score += 1

            # feature importance
            if r.get("feature_code") in {"PPLC", "PPLA"}:
                score += 2

            candidate = {
                "score": score,
                "lat": lat,
                "lon": lon,
                "name": r.get("name"),
                "country": r.get("country"),
                "country_code": cc
            }

            candidates.append(candidate)

        # -------------------------
        # 🔥 EARLY EXIT (huge win)
        # -------------------------
        if candidates:
            best_local = max(candidates, key=lambda x: x["score"])
            if best_local["score"] >= 10:
                set_geo_cache(cache_key, best_local)
                return best_local

    # -------------------------
    # 6. Final selection
    # -------------------------
    if not candidates:
        logger.warning(f"Geolocation failed for '{city_name}'")
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    set_geo_cache(cache_key, best)

    logger.info(
        f"Geolocated '{city_name}' → {best['name']}, {best['country']} "
        f"({best['lat']}, {best['lon']}) score={best['score']}"
    )

    return best
