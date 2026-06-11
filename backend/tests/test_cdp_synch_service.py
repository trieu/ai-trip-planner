import asyncio
from arango import ArangoClient

# Import your centralized settings to get DB credentials
from config import get_settings

from services.database.ag_profile_repository import ArangoProfileRepository

# Note: Using PostgresProfileService based on your cdp_profile_service.py definition
from services.cdp_profile_service import PostgresProfileService
from services.cdp_sync_service import ArangoToPostgresSyncService

settings = get_settings()


def perform_sync_task(tenant_id: str, segment_id: str) -> int:
    """
    Synchronous wrapper to execute the ArangoDB to PostgreSQL profile sync task.
    Ideal for Celery/Dramatiq worker execution.
    """

    # 1. Initialize ArangoDB Client and Database connection
    client = ArangoClient(hosts=settings.ARANGO_HOST)
    arango_db = client.db(
        settings.ARANGO_DB,
        username=settings.ARANGO_USER,
        password=settings.ARANGO_PASSWORD,
    )

    # Pass the active db connection to the Arango repository
    arango_repo = ArangoProfileRepository(db=arango_db)

    # 2. Initialize PostgreSQL Service
    # Uses the derived PGSQL_DATABASE_DSN property from your config.py Settings
    if not settings.PGSQL_DATABASE_DSN:
        raise ValueError("PostgreSQL DSN is not properly configured in settings.")

    pg_repo = PostgresProfileService(db_url=settings.PGSQL_DATABASE_DSN)

    # 3. Initialize the Sync Service
    service = ArangoToPostgresSyncService(arango_repo, pg_repo, tenant_id)

    # 4. Trigger the async flow from this synchronous worker:
    # asyncio.run() creates a new event loop, runs the async function, and closes the loop.
    synced_count = asyncio.run(service.sync_segment(segment_id=segment_id))

    return synced_count
