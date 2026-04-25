import json
import logging
import random
from typing import Any, Dict

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text

from services.data_service import BaseProfileService, require_env
from tools.cache_utils import get_cache, set_cache_with_ttl

logger = logging.getLogger("postgres_profile_service")

PROFILE_CACHE_TTL = 600  # 10 minutes

PROFILE_SQL = """
    SELECT *
    FROM cdp_profiles
    WHERE tenant_id = :tenant_id
    AND profile_id = :user_id
    LIMIT 1;
"""


def build_pg_dsn(prefix: str = "PGSQL_DB") -> str:
    return (
        f"postgresql+asyncpg://"
        f"{require_env(f'{prefix}_USER')}:"
        f"{require_env(f'{prefix}_PASSWORD')}@"
        f"{require_env(f'{prefix}_HOST', 'localhost')}:"
        f"{require_env(f'{prefix}_PORT', '5432')}/"
        f"{require_env(f'{prefix}_NAME')}"
    )


def create_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=10,
        max_overflow=20,
        pool_timeout=5,
        pool_recycle=1800,
        pool_pre_ping=True,
    )


def build_engines():
    engines = [create_engine(build_pg_dsn())]

    for i in range(1, 4):
        prefix = f"PGSQL_REPLICA_{i}"
        try:
            if require_env(f"{prefix}_HOST", None):
                engines.append(create_engine(build_pg_dsn(prefix)))
        except Exception:
            continue

    return engines


class PostgresProfileService(BaseProfileService):
    def __init__(self):
        self.engines = build_engines()

    def _pick_engine(self) -> AsyncEngine:
        return random.choice(self.engines)

    def _cache_key(self, tenant_id: str, user_id: str) -> str:
        return f"profile:{tenant_id}:{user_id}"

    async def get_user_profile(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        cache_key = self._cache_key(tenant_id, user_id)

        # ==========================
        # 1. CACHE HIT
        # ==========================
        cached = get_cache(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                logger.warning("Cache decode failed")

        # ==========================
        # 2. DB QUERY
        # ==========================
        engine = self._pick_engine()

        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text(PROFILE_SQL),
                    {"tenant_id": tenant_id, "user_id": user_id}
                )

                row = result.mappings().first()  # ✅ FIXED

                if not row:
                    return {}

                profile = dict(row)

                # ==========================
                # 3. CACHE SET
                # ==========================
                set_cache_with_ttl(cache_key, PROFILE_CACHE_TTL, json.dumps(profile, default=str))

                return profile

        except Exception as e:
            return {
                "error": "postgres_unavailable",
                "detail": str(e),
            }
