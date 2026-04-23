import logging
from typing import Any, Dict, Optional

import redis
import json
import os

from tools.text_utils import normalize_text

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("agentic_tools.cache_utils")

# ============================================================
# Redis Cache (1-hour TTL)
# ============================================================


REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", 3600))
GEO_TTL = 86400  # 24 hours for geocoding results

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True  # return str instead of bytes
)


def make_cache_key(location: str, unit: str) -> str:
    normalized = normalize_text(location)
    return f"weather:{normalized}:{unit}"


def get_cache(key: str) -> Optional[str]:
    try:
        return redis_client.get(key)
    except Exception as e:
        logger.warning(f"Redis GET failed: {e}")
        return None


def set_cache(key: str, value: str):
    try:
        redis_client.setex(key, REDIS_CACHE_TTL, value)
    except Exception as e:
        logger.warning(f"Redis SET failed: {e}")


def geo_cache_key(city: str) -> str:
    return f"geo:{normalize_text(city)}"


def get_geo_cache(key: str) -> Optional[Dict[str, Any]]:
    try:
        val = redis_client.get(key)
        return json.loads(val) if val else None
    except Exception as e:
        logger.warning(f"Redis GET geo failed: {e}")
        return None


def set_geo_cache(key: str, value: Dict[str, Any]):
    try:
        redis_client.setex(key, GEO_TTL, json.dumps(value))
    except Exception as e:
        logger.warning(f"Redis SET geo failed: {e}")