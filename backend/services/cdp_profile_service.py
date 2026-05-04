from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from tools.cache_utils import get_cache, set_cache_with_ttl
from services.data_models.pg_profile import PGProfileUpsert

logger = logging.getLogger(__name__)


class PostgresProfileService:
    """
    SQLAlchemy Async Service (asyncpg-based)

    - Multi-tenant safe
    - UPSERT via raw SQL
    - Search + filtering
    """

    def __init__(self, db_url: str):
        """
        Example:
        postgresql+asyncpg://user:pass@localhost:5432/db
        """
        self.engine = create_async_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )

        self.async_session = sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        
    def _cache_key(self, tenant_id: str, user_id: str) -> str:
        return f"profile:{tenant_id}:{user_id}"

    # =====================================================
    # UPSERT
    # =====================================================
    async def upsert_profile(self, profile: PGProfileUpsert) -> None:
        query = text("""
        INSERT INTO cdp_profiles (
            tenant_id, profile_id,
            identities,
            primary_email, secondary_emails,
            primary_phone, secondary_phones,
            first_name, last_name,
            living_location, living_country, living_city,
            job_titles, data_labels, content_keywords,
            media_channels, behavioral_events,
            segments, journey_maps,
            event_statistics, top_engaged_touchpoints,
            ext_data,
            updated_at
        )
        VALUES (
            :tenant_id, :profile_id,
            :identities,
            :primary_email, :secondary_emails,
            :primary_phone, :secondary_phones,
            :first_name, :last_name,
            :living_location, :living_country, :living_city,
            :job_titles, :data_labels, :content_keywords,
            :media_channels, :behavioral_events,
            :segments, :journey_maps,
            :event_statistics, :top_engaged_touchpoints,
            :ext_data,
            NOW()
        )
        ON CONFLICT (tenant_id, profile_id)
        DO UPDATE SET
            identities = EXCLUDED.identities,
            primary_email = EXCLUDED.primary_email,
            secondary_emails = EXCLUDED.secondary_emails,
            primary_phone = EXCLUDED.primary_phone,
            secondary_phones = EXCLUDED.secondary_phones,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            living_location = EXCLUDED.living_location,
            living_country = EXCLUDED.living_country,
            living_city = EXCLUDED.living_city,
            job_titles = EXCLUDED.job_titles,
            data_labels = EXCLUDED.data_labels,
            content_keywords = EXCLUDED.content_keywords,
            media_channels = EXCLUDED.media_channels,
            behavioral_events = EXCLUDED.behavioral_events,
            segments = EXCLUDED.segments,
            journey_maps = EXCLUDED.journey_maps,
            event_statistics = EXCLUDED.event_statistics,
            top_engaged_touchpoints = EXCLUDED.top_engaged_touchpoints,
            ext_data = EXCLUDED.ext_data,
            updated_at = NOW()
        """)

        async with self.async_session() as session:
            await session.execute(query, profile.to_pg_row())
            await session.commit()

    # =====================================================
    # GET
    # =====================================================
    async def get_user_profile(
        self,
        tenant_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """ Get user profile by tenant_id + user_id
            Implements a simple cache-aside pattern with Redis (or in-memory) cache.   
        
        """

        cache_key = self._cache_key(tenant_id, user_id)

        # -------------------------
        # CACHE HIT
        # -------------------------
        try:
            cached = get_cache(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            logger.warning("Cache corrupted for key=%s", cache_key)

        # -------------------------
        # DB FETCH
        # -------------------------
        query = text("""
        SELECT *
        FROM cdp_profiles
        WHERE tenant_id = :tenant_id
        AND profile_id = :profile_id
        LIMIT 1
        """)

        try:
            async with self.async_session() as session:
                result = await session.execute(
                    query,
                    {"tenant_id": tenant_id, "profile_id": user_id}
                )
                row = result.mappings().first()

                if not row:
                    return {}

                data = dict(row)

                # -------------------------
                # CACHE SET
                # -------------------------
                try:
                    set_cache_with_ttl(cache_key, json.dumps(data))
                except Exception:
                    pass

                return data

        except Exception as e:
            logger.error("Postgres error: %s", e)
            return {"error": "postgres_unavailable"}

    # =====================================================
    # DELETE
    # =====================================================
    async def delete_profile(
        self,
        tenant_id: str,
        profile_id: str
    ) -> bool:
        query = text("""
        DELETE FROM cdp_profiles
        WHERE tenant_id = :tenant_id
          AND profile_id = :profile_id
        """)

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {"tenant_id": tenant_id, "profile_id": profile_id}
            )
            await session.commit()
            return result.rowcount > 0

    # =====================================================
    # SEARCH
    # =====================================================
    async def search_profiles(
        self,
        tenant_id: str,
        keyword: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:

        conditions = ["tenant_id = :tenant_id"]
        params: Dict[str, Any] = {"tenant_id": tenant_id}

        if keyword:
            conditions.append("""
                (
                    first_name ILIKE :kw OR
                    last_name ILIKE :kw OR
                    primary_email ILIKE :kw
                )
            """)
            params["kw"] = f"%{keyword}%"

        where_clause = " AND ".join(conditions)

        query = text(f"""
        SELECT *
        FROM cdp_profiles
        WHERE {where_clause}
        ORDER BY updated_at DESC
        LIMIT :limit OFFSET :offset
        """)

        params["limit"] = limit
        params["offset"] = offset

        async with self.async_session() as session:
            result = await session.execute(query, params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    # =====================================================
    # GET PROFILES BY SEGMENT
    # =====================================================
    async def get_profiles_by_segment(
        self,
        tenant_id: str,
        segment_id: str,
        limit: int = 50,
        offset: int = 0,
    ):
        """ GET PROFILES BY SEGMENT

        Args:
            tenant_id (str): _description_
            segment_id (str): _description_
            limit (int, optional): _description_. Defaults to 50.
            offset (int, optional): _description_. Defaults to 0.

        Returns:
            _type_: _description_
        """
        return await self.filter_profiles(
            tenant_id,
            filters={"segment_id": segment_id},
            limit=limit,
            offset=offset,
        )

    # =====================================================
    # GET PROFILES BY DATA LABEL
    # =====================================================
    async def get_profiles_by_data_label(
        self,
        tenant_id: str,
        label: str,
        limit: int = 50,
    ):
        """ GET PROFILES BY DATA LABEL

        Args:
            tenant_id (str): _description_
            label (str): _description_
            limit (int, optional): _description_. Defaults to 50.

        Returns:
            _type_: _description_
        """
        return await self.filter_profiles(
            tenant_id,
            filters={"data_label": label},
            limit=limit,
        )

    # =====================================================
    # GET PROFILES BY CITY
    # =====================================================
    async def get_profiles_by_city(
        self,
        tenant_id: str,
        city: str,
        limit: int = 50,
    ):
        """ GET PROFILES BY CITY

        Args:
            tenant_id (str): _description_
            city (str): _description_
            limit (int, optional): _description_. Defaults to 50.

        Returns:
            _type_: _description_
        """
        return await self.filter_profiles(
            tenant_id,
            filters={"living_city": city},
            limit=limit,
        )

    # =====================================================
    # FILTER (ARBITRARY FIELDS)
    # =====================================================
    async def filter_profiles(
        self,
        tenant_id: str,
        filters: Dict[str, Any],
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:

        filters["tenant_id"] = tenant_id

        where_clause, params = self._build_filter_query(filters)

        query = text(f"""
        SELECT *
        FROM cdp_profiles
        WHERE {where_clause}
        ORDER BY updated_at DESC
        LIMIT :limit OFFSET :offset
        """)

        params["limit"] = limit
        params["offset"] = offset

        async with self.async_session() as session:
            result = await session.execute(query, params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    # =====================================================
    # GET PROFILES BY MEDIA CHANNEL
    # =====================================================
    async def get_profiles_by_media_channel(
        self,
        tenant_id: str,
        channel: str,
        limit: int = 50,
    ):
        """ GET PROFILES BY MEDIA CHANNEL

        Args:
            tenant_id (str): _description_
            channel (str): _description_
            limit (int, optional): _description_. Defaults to 50.

        Returns:
            _type_: _description_
        """
        return await self.filter_profiles(
            tenant_id,
            filters={"media_channel": channel},
            limit=limit,
        )

    # =====================================================
    # Batch Fetch (for ML / scoring)
    # =====================================================
    async def get_profiles_batch(
        self,
        tenant_id: str,
        limit: int = 1000,
        offset: int = 0,
    ):
        """ Batch Fetch
        For data sync / migration use cases.  

        Args:
            tenant_id (str): _description_  
            limit (int, optional): _description_. Defaults to 1000.
            offset (int, optional): _description_. Defaults to 0.
        """

        query = text("""
            SELECT *
            FROM cdp_profiles
            WHERE tenant_id = :tenant_id
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """)

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {"tenant_id": tenant_id, "limit": limit, "offset": offset}
            )
            return [dict(r) for r in result.mappings().all()]

    # =====================================================
    # COUNT PROFILES (with filters)
    # =====================================================

    async def count_profiles(
        self,
        tenant_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """ Count Profiles (with filters)
        Useful for pagination, analytics, etc.
        Args:
            tenant_id (str): _description_
            filters (Optional[Dict[str, Any]], optional): _description_. Defaults to None. 
        Returns:
            int:  COUNT PROFILES  """

        filters = filters or {}
        filters["tenant_id"] = tenant_id

        where_clause, params = self._build_filter_query(filters)

        query = text(f"""
        SELECT COUNT(*) as total
        FROM cdp_profiles
        WHERE {where_clause}
        """)

        async with self.async_session() as session:
            result = await session.execute(query, params)
            return result.scalar_one()

    # =====================================================
    # INTERNAL: BUILD FILTER QUERY
    # =====================================================
    def _build_filter_query(self, filters: Dict[str, Any]) -> (str, Dict[str, Any]):
        conditions = ["tenant_id = :tenant_id"]
        params = {"tenant_id": filters["tenant_id"]}

        # -------------------------
        # SIMPLE FIELDS
        # -------------------------
        if filters.get("living_city"):
            conditions.append("living_city = :living_city")
            params["living_city"] = filters["living_city"]

        if filters.get("primary_email"):
            conditions.append("primary_email = :primary_email")
            params["primary_email"] = filters["primary_email"]

        # -------------------------
        # ARRAY / JSONB (GIN index)
        # -------------------------
        if filters.get("data_label"):
            conditions.append("data_labels ? :data_label")
            params["data_label"] = filters["data_label"]

        if filters.get("media_channel"):
            conditions.append("media_channels ? :media_channel")
            params["media_channel"] = filters["media_channel"]

        if filters.get("behavior_event"):
            conditions.append("behavioral_events ? :behavior_event")
            params["behavior_event"] = filters["behavior_event"]

        # -------------------------
        # SEGMENTS (JSONB complex)
        # segments: [{id, name, score}]
        # -------------------------
        if filters.get("segment_id"):
            conditions.append("""
            EXISTS (
                SELECT 1 FROM jsonb_array_elements(segments) seg
                WHERE seg->>'id' = :segment_id
            )
            """)
            params["segment_id"] = filters["segment_id"]

        # -------------------------
        # TOUCHPOINTS
        # -------------------------
        if filters.get("touchpoint"):
            conditions.append("""
            EXISTS (
                SELECT 1 FROM jsonb_array_elements(top_engaged_touchpoints) tp
                WHERE tp->>'channel' = :touchpoint
            )
            """)
            params["touchpoint"] = filters["touchpoint"]

        # -------------------------
        # KEYWORD SEARCH
        # -------------------------
        if filters.get("keyword"):
            conditions.append("""
            (
                first_name ILIKE :kw OR
                last_name ILIKE :kw OR
                primary_email ILIKE :kw
            )
            """)
            params["kw"] = f"%{filters['keyword']}%"

        where_clause = " AND ".join(conditions)
        return where_clause, params
