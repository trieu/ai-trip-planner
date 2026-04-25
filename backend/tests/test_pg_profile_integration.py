
import pytest
import logging
from services.pgsql_service import PostgresProfileService


TEST_TENANT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_PROFILE_ID = "00000000-0000-0000-0000-000000000002"
EXPECTED_EMAIL = "bob.safe@test.com"

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_get_user_profile_real_db():
    """
    Integration test against real PostgreSQL (AGE schema).
    Requires:
    - DB running
    - Correct env vars
    - Test data present
    """

    service = PostgresProfileService()

    result = await service.get_user_profile(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_PROFILE_ID
    )
    
    logger.info(f"Retrieved profile: {result}")

    assert result, "Profile should not be empty"

    # adjust depending on your column structure
    email = result.get("primary_email")
    logger.info(f"Retrieved email: {email}")
    assert email == EXPECTED_EMAIL