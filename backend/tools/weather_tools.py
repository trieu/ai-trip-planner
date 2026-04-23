import logging
import requests

from typing import Dict, Any, Optional, List
from langchain_core.tools import tool

from tools.cache_utils import geo_cache_key, get_geo_cache, make_cache_key, get_cache, set_cache, set_geo_cache
from tools.text_utils import canonicalize_city_name, looks_vietnamese, normalize_text


# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("agentic_tools.weather_tools")

# ============================================================
# Public tool function (REQUIRES DOCSTRING)
# ============================================================


@tool
def get_current_weather(location: str, unit: str = "celsius") -> str:
    """
    Get the current weather for a city or location name. <br>

    The function automatically: <br>
    - Normalizes and resolves the location name <br>
    - Converts it into latitude and longitude <br>
    - Fetches real-time weather data from Open-Meteo <br>

    Args:
        location: City or place name (e.g., "Da Nang", "Paris", "HCMC"). <br>
        unit: Temperature unit, either "celsius" or "fahrenheit". <br>

    Returns:
        A string description of the current weather including temperature, condition, and wind speed.
    """
    unit = unit.lower()
    if unit not in {"celsius", "fahrenheit"}:
        return "Invalid unit. Please use 'celsius' or 'fahrenheit'."

    key_hint = f"{location}:{unit}"
    cache_key = make_cache_key(key_hint, unit)

    # ✅ CACHE FIRST
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[CACHE HIT] {cache_key}")
        return cached

    coords = get_coordinates(location)
    if not coords:
        logger.info(f"Geocoding failed for '{location}'")
        return f"Location not found: {location}"

    weather_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "current_weather": "true",
        "temperature_unit": unit
    }

    # SAFE API CALL with error handling and logging
    try:
        resp = requests.get(weather_url, params=params, timeout=9)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current_weather", {})

        temp = current.get("temperature")
        unit_symbol = "°C" if unit == "celsius" else "°F"
        windspeed = current.get("windspeed")

        result = (
            f"Current weather in {coords['name']}, {coords['country']}: "
            f"{temp}{unit_symbol}, wind speed {windspeed} km/h."
        )

        # ✅ STORE CACHE
        set_cache(cache_key, result)

        return result

    except requests.RequestException as e:
        logger.error(f"Weather API error: {e}")
        return "Weather service unreachable. Please try again later."


# ============================================================
# Geocoding
# ============================================================


def get_coordinates(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a city name to geographic coordinates.

    This function applies multiple accuracy strategies:
    - Unicode normalization and alias resolution
    - Language fallback (vi → en)
    - Country bias (Vietnam when detected)
    - Candidate ranking instead of first-hit selection

    Args:
        city_name: City or location name provided by the user.

    Returns:
        Dictionary containing latitude, longitude, resolved name, and country
        if successful; otherwise None.
    """
    # -------------------------
    # 1. Validate input
    # -------------------------
    if not city_name or not isinstance(city_name, str):
        logger.warning(f"Invalid city_name: {city_name}")
        return None

    city_name = city_name.strip()
    if len(city_name) < 2:
        return None

    # -------------------------
    # 2. Cache lookup
    # -------------------------
    cache_key = geo_cache_key(city_name)
    cached = get_geo_cache(cache_key)
    if cached:
        logger.info(f"[GEO CACHE HIT] {city_name}")
        return cached

    # -------------------------
    # 3. Prepare attempts
    # -------------------------
    geo_url = "https://geocoding-api.open-meteo.com/v1/search"

    canonical = canonicalize_city_name(city_name)
    country_bias = "VN" if looks_vietnamese(city_name) else None

    attempts = [
        (city_name, "en"),
        (city_name, "vi"),
        (canonical, "vi"),
        (canonical, "en"),
    ]

    seen = set()
    candidates: List[Dict[str, Any]] = []

    # -------------------------
    # 4. Query API safely
    # -------------------------
    for name, lang in attempts:
        key = (name, lang)
        if key in seen:
            continue
        seen.add(key)

        data = _safe_request(
            geo_url,
            {
                "name": name,
                "count": 5,
                "language": lang,
                "format": "json"
            }
        )

        if not data:
            continue

        results = data.get("results")
        if not isinstance(results, list):
            continue

        for r in results:
            try:
                lat = r.get("latitude")
                lon = r.get("longitude")

                if lat is None or lon is None:
                    continue

                score = 0

                # country bias
                if country_bias and r.get("country_code") == country_bias:
                    score += 3

                # population weight
                pop = r.get("population") or 0
                if pop > 1_000_000:
                    score += 2
                elif pop > 100_000:
                    score += 1

                # name similarity
                resolved = normalize_text(r.get("name", ""))
                if resolved == canonical:
                    score += 4
                elif canonical in resolved:
                    score += 2

                # feature importance (capital, admin)
                if r.get("feature_code") in {"PPLC", "PPLA"}:
                    score += 2

                candidates.append({
                    "score": score,
                    "lat": lat,
                    "lon": lon,
                    "name": r.get("name"),
                    "country": r.get("country"),
                    "country_code": r.get("country_code")
                })

            except Exception as e:
                logger.debug(f"Candidate parse error: {e}")
                continue

    # -------------------------
    # 5. Final selection
    # -------------------------
    if not candidates:
        logger.warning(f"Geolocation failed for '{city_name}'")
        return None

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    # -------------------------
    # 6. Cache result
    # -------------------------
    set_geo_cache(cache_key, best)

    logger.info(
        f"Geolocated '{city_name}' → {best['name']}, {best['country']} "
        f"({best['lat']}, {best['lon']}) score={best['score']}"
    )

    return best

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

# ============================================================
# Weather helpers
# ============================================================


def get_weather_description(code: int) -> str:
    """
    Convert WMO weather codes into human-readable descriptions.

    Args:
        code: Integer weather code from Open-Meteo.

    Returns:
        Textual description of the weather condition.
    """
    wmo_codes = {
        0: "Clear sky",
        1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Depositing rime fog",
        51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        95: "Thunderstorm", 96: "Thunderstorm with hail"
    }
    return wmo_codes.get(code, "Unknown")
