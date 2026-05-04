import pytest
import os
import uuid

from sqlalchemy import text

from services.cdp_profile_service import PostgresProfileService
from services.data_models.pg_profile import PGProfileUpsert
from config import Settings

TEST_TENANT_ID = str(uuid.uuid4())
TEST_PROFILE_ID = str(uuid.uuid4())

PGSQL_DATABASE_DSN = Settings().PGSQL_DATABASE_DSN

if not PGSQL_DATABASE_DSN:
    pytest.skip("Postgres not configured", allow_module_level=True)


@pytest.fixture
async def service():
    svc = PostgresProfileService(db_url=PGSQL_DATABASE_DSN)
    yield svc


async def ensure_test_tenant(service, tenant_id: str):
    query = text("""
    INSERT INTO tenant (tenant_id, tenant_name, keycloak_realm)
    VALUES (:id, 'test_tenant', 'test_realm')
    ON CONFLICT (keycloak_realm, tenant_name) DO NOTHING
    """)

    async with service.async_session() as session:
        await session.execute(query, {"id": tenant_id})
        await session.commit()


@pytest.mark.asyncio
async def test_upsert_and_get_profile(service: PostgresProfileService):
    await ensure_test_tenant(service, TEST_TENANT_ID)

    profile = PGProfileUpsert(
        tenant_id=TEST_TENANT_ID,
        profile_id=TEST_PROFILE_ID,
        primary_email="test.user@example.com",
        first_name="Test",
        last_name="User",
        living_city="HCM",
        data_labels=["vip", "beta_user"],
    )

    await service.upsert_profile(profile)

    result = await service.get_user_profile(
        tenant_id=TEST_TENANT_ID,
        user_id=TEST_PROFILE_ID
    )

    assert result is not None
    assert result["primary_email"] == "test.user@example.com"


@pytest.mark.asyncio
async def test_search_profiles(service: PostgresProfileService):
    await ensure_test_tenant(service, TEST_TENANT_ID)

    profile = PGProfileUpsert(
        tenant_id=TEST_TENANT_ID,
        profile_id=TEST_PROFILE_ID,
        first_name="Test",
        primary_email="test.user@example.com",
    )

    await service.upsert_profile(profile)

    results = await service.search_profiles(
        tenant_id=TEST_TENANT_ID,
        keyword="Test",
        limit=10
    )

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_delete_profile(service: PostgresProfileService):
    await ensure_test_tenant(service, TEST_TENANT_ID)

    profile = PGProfileUpsert(
        tenant_id=TEST_TENANT_ID,
        profile_id=TEST_PROFILE_ID,
        primary_email="test.user@example.com",
    )

    await service.upsert_profile(profile)

    deleted = await service.delete_profile(
        tenant_id=TEST_TENANT_ID,
        profile_id=TEST_PROFILE_ID
    )

    assert deleted is True
