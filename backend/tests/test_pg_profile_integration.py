# tests/test_pg_profile_integration.py

import pytest
import logging
import os

from services.pgsql_service import PostgresProfileService


TEST_TENANT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_PROFILE_ID = "00000000-0000-0000-0000-000000000002"
EXPECTED_EMAIL = "bob.safe@test.com"

logger = logging.getLogger(__name__)


# --------------------------------------------------
# SKIP IF DB NOT CONFIGURED
# --------------------------------------------------
if not os.getenv("PGSQL_DB_USER"):
    pytest.skip("Postgres not configured", allow_module_level=True)


@pytest.mark.asyncio
async def test_get_user_profile_real_db():
    service = PostgresProfileService()

    result = await service.get_user_profile(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_PROFILE_ID
    )

    logger.info(f"Retrieved profile: {result}")

    assert result, "Profile should not be empty"

    email = result.get("primary_email")
    logger.info(f"Retrieved email: {email}")

    assert email == EXPECTED_EMAIL