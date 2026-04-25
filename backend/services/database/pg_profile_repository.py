"""Repository for managing PostgreSQL profiles."""


UPSERT_PROFILE_SQL = """
    INSERT INTO cdp_profiles (
                tenant_id,
                profile_id,

                -- identities
                identities,

                -- contact
                primary_email,
                secondary_emails,
                primary_phone,
                secondary_phones,

                -- personal & location
                first_name,
                last_name,
                living_location,
                living_country,
                living_city,

                -- enrichment
                job_titles,
                data_labels,
                content_keywords,
                media_channels,
                behavioral_events,

                -- segmentation & journeys
                segments,
                journey_maps,

                -- statistics & touchpoints
                event_statistics,
                top_engaged_touchpoints,

                -- extensibility
                ext_data
            )
            VALUES (
                %(tenant_id)s,
                %(profile_id)s,

                %(identities)s::jsonb,

                %(primary_email)s,
                %(secondary_emails)s::jsonb,
                %(primary_phone)s,
                %(secondary_phones)s::jsonb,

                %(first_name)s,
                %(last_name)s,
                %(living_location)s,
                %(living_country)s,
                %(living_city)s,

                %(job_titles)s::jsonb,
                %(data_labels)s::jsonb,
                %(content_keywords)s::jsonb,
                %(media_channels)s::jsonb,
                %(behavioral_events)s::jsonb,

                %(segments)s::jsonb,
                %(journey_maps)s::jsonb,

                %(event_statistics)s::jsonb,
                %(top_engaged_touchpoints)s::jsonb,

                %(ext_data)s::jsonb
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

                ext_data = EXCLUDED.ext_data;
"""


import json
import logging
from typing import List, Dict, Any, Union, Optional

import psycopg
from sqlalchemy.orm import Session

from data_models.pg_profile import PGProfileUpsert

logger = logging.getLogger(__name__)


class PGProfileRepository:
    """ 
    PostgreSQL repository for profiles management.
    Supports both psycopg.Connection and sqlalchemy.orm.Session.
    """

    def __init__(self, bind: Union[psycopg.Connection, Session]):
        """
        Initialize the repository with a connection or session.
        If a Session is provided, extract the raw psycopg driver connection.
        """
        if hasattr(bind, "connection"):  # It's a SQLAlchemy Session
            # We get the underlying psycopg3 connection object
            self.conn = bind.connection().connection.driver_connection
        else:  # It's already a psycopg Connection
            self.conn = bind

    def _execute_fetch(self, query: str, params: tuple) -> List[Dict[str, Any]]:
        """Helper to execute a query and return results as a list of dictionaries."""
        with self.conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()

    # =========================================================================
    # 0. Upsert profile
    # ========================================================================= 
    def upsert_profile(self, profile: PGProfileUpsert) -> None:
        """
        Upsert a CDP profile synced from ArangoDB.
        """
        with self.conn.cursor() as cur:
            cur.execute(UPSERT_PROFILE_SQL, profile.to_pg_row())
        # Removed self.conn.commit() -> Let the service/context manager handle it

    # =========================================================================
    # 1. Search & Load Methods
    # =========================================================================

    def load_profiles_by_segment_or_journey(self, tenant_id: str, segment_id: str = None, journey_id: str = None) -> List[Dict[str, Any]]:
        if segment_id:
            sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND segments @> %s::jsonb"
            param_json = json.dumps([{"id": segment_id}])
            return self._execute_fetch(sql, (tenant_id, param_json))

        if journey_id:
            sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND journey_maps @> %s::jsonb"
            param_json = json.dumps([{"id": journey_id}])
            return self._execute_fetch(sql, (tenant_id, param_json))
        return []

    def search_profiles_by_data_label(self, tenant_id: str, label: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND data_labels ? %s"
        return self._execute_fetch(sql, (tenant_id, label))

    def load_profile_by_email(self, tenant_id: str, email: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND (primary_email = %s OR secondary_emails @> %s::jsonb)"
        return self._execute_fetch(sql, (tenant_id, email, json.dumps([email])))

    def load_profile_by_phone(self, tenant_id: str, phone: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND (primary_phone = %s OR secondary_phones @> %s::jsonb)"
        return self._execute_fetch(sql, (tenant_id, phone, json.dumps([phone])))

    def load_profiles_by_identity(self, tenant_id: str, identity_string: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND identities ? %s"
        return self._execute_fetch(sql, (tenant_id, identity_string))

    def search_profiles_by_living_city(self, tenant_id: str, city: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND living_city = %s"
        return self._execute_fetch(sql, (tenant_id, city))

    def search_profiles_by_content_keyword(self, tenant_id: str, keyword: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND content_keywords ? %s"
        return self._execute_fetch(sql, (tenant_id, keyword))

    def search_profiles_by_media_channel(self, tenant_id: str, channel: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND media_channels ? %s"
        return self._execute_fetch(sql, (tenant_id, channel))

    def search_profiles_by_behavioral_event_label(self, tenant_id: str, event_label: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND behavioral_events ? %s"
        return self._execute_fetch(sql, (tenant_id, event_label))

    def search_profiles_by_event_statistic_key(self, tenant_id: str, stat_key: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND event_statistics ? %s"
        return self._execute_fetch(sql, (tenant_id, stat_key))

    def search_profiles_by_touchpoint_key(self, tenant_id: str, touchpoint_key: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND top_engaged_touchpoints @> %s::jsonb"
        param_json = json.dumps([{"_key": touchpoint_key}])
        return self._execute_fetch(sql, (tenant_id, param_json))

    def search_profiles_by_job_title(self, tenant_id: str, job_title: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM cdp_profiles WHERE tenant_id = %s AND job_titles ? %s"
        return self._execute_fetch(sql, (tenant_id, job_title))