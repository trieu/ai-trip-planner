import logging
import os
from datetime import datetime, timezone
from typing import Optional

import redis
import dramatiq
from periodiq import cron

from services.data_models.dbo_tenant import resolve_tenant_id
from services.sync_profiles_service import run_synch_profiles

from config import Settings

DRAMATIQ_REDIS_URL = Settings().DRAMATIQ_REDIS_URL
DRAMATIQ_SYNC_PROFILES_CRON = Settings().DRAMATIQ_SYNC_PROFILES_CRON

logger = logging.getLogger(__name__)
redis_client = redis.from_url(DRAMATIQ_REDIS_URL)


def _build_last_sync_key(
    *,
    segment_id: Optional[str] = None,
    segment_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Build a deterministic Redis key for incremental sync checkpoints.
    """
    if segment_id:
        return f"leo_cdp:{tenant_id}:segment:{segment_id}:last_sync"
    return f"leo_cdp:{tenant_id}:segment_name:{segment_name}:last_sync"


# --------------------------------------------------
# Dramatiq Actor (Task)
# --------------------------------------------------


# max_retries handles autoretry_for=(Exception) with exponential backoff by default.
@dramatiq.actor(max_retries=3, periodic=cron(DRAMATIQ_SYNC_PROFILES_CRON))
def sync_profiles_task(
    segment_id: Optional[str] = None,
    segment_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """
    Incremental Sync Task via Dramatiq
    - Sync profiles by segment_id OR segment_name
    - Exactly one must be provided
    """

    # Assuming a placeholder for your default tenant logic
    if not tenant_id:
        tenant_id = "00000000-0000-0000-0000-000000000000"

    # Validation (fail fast, fail loud)
    if bool(segment_id) == bool(segment_name):
        raise ValueError(
            "Exactly one of `segment_id` or `segment_name` must be provided."
        )

    logger.info(
        "Starting profile sync | tenant=%s | segment_id=%s | segment_name=%s",
        tenant_id,
        segment_id,
        segment_name,
    )

    # Load last checkpoint
    last_sync_key = _build_last_sync_key(
        segment_id=segment_id, segment_name=segment_name, tenant_id=tenant_id
    )

    last_sync_ts = redis_client.get(last_sync_key)
    if last_sync_ts:
        last_sync_ts = last_sync_ts.decode("utf-8")
    else:
        last_sync_ts = "1970-01-01T00:00:00Z"

    current_run_time = datetime.now(timezone.utc).isoformat()

    logger.info("Last sync timestamp: %s", last_sync_ts)

    # Execute sync
    try:
        run_synch_profiles(
            segment_id=segment_id,
            segment_name=segment_name,
            tenant_id=tenant_id,
            last_sync_ts=last_sync_ts,
        )

        # Persist checkpoint ONLY on success
        redis_client.set(last_sync_key, current_run_time)

        logger.info(
            "Sync completed | tenant=%s | segment=%s",
            tenant_id,
            segment_id or segment_name,
        )

    except Exception as exc:
        logger.exception("Profile sync failed")
        raise exc
