
import logging
import requests

from langchain_core.tools import tool

from tools.location_utils import get_coordinates
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


