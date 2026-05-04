import pytest
import uuid

from sqlalchemy import text

from services.cdp_profile_service import PostgresProfileService
from services.data_models.pg_profile import PGProfileUpsert
from config import Settings

PGSQL_DATABASE_DSN = Settings().PGSQL_DATABASE_DSN

if not PGSQL_DATABASE_DSN:
    pytest.skip("Postgres not configured", allow_module_level=True)


# =====================================================
# FIXTURE (ISOLATED PER TEST)
# =====================================================
@pytest.fixture
async def service():
    svc = PostgresProfileService(db_url=PGSQL_DATABASE_DSN)
    yield svc


@pytest.fixture
async def tenant(service):
    tenant_id = str(uuid.uuid4())

    async with service.async_session() as session:
        await session.execute(text("""
            INSERT INTO tenant (tenant_id, tenant_name, keycloak_realm)
            VALUES (:tenant_id, :tenant_name, :realm)
        """), {
            "tenant_id": tenant_id,
            "tenant_name": f"test_{tenant_id[:6]}",
            "realm": "test_realm"
        })
        await session.commit()

    yield tenant_id

    # -----------------------------
    # CLEANUP (profiles + tenant)
    # -----------------------------
    async with service.async_session() as session:
        await session.execute(
            text("DELETE FROM cdp_profiles WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        )
        await session.execute(
            text("DELETE FROM tenant WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        )
        await session.commit()


# =====================================================
# UPSERT + GET
# =====================================================
@pytest.mark.asyncio
async def test_upsert_and_get_profile(service, tenant):
    profile_id = str(uuid.uuid4())

    profile = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=profile_id,
        primary_email="test.user@example.com",
        first_name="Test",
        last_name="User",
        living_city="HCM",
        data_labels=["vip", "beta_user"],
    )

    await service.upsert_profile(profile)

    result = await service.get_user_profile(
        tenant_id=tenant,
        user_id=profile_id
    )

    assert result is not None
    assert result["primary_email"] == "test.user@example.com"


# =====================================================
# SEARCH
# =====================================================
@pytest.mark.asyncio
async def test_search_profiles(service, tenant):
    profile_id = str(uuid.uuid4())

    profile = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=profile_id,
        first_name="Test",
        primary_email="test.user@example.com",
    )

    await service.upsert_profile(profile)

    results = await service.search_profiles(
        tenant_id=tenant,
        keyword="Test",
        limit=10
    )

    assert len(results) >= 1


# =====================================================
# DELETE
# =====================================================
@pytest.mark.asyncio
async def test_delete_profile(service, tenant):
    profile_id = str(uuid.uuid4())

    profile = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=profile_id,
        primary_email="test.user@example.com",
    )

    await service.upsert_profile(profile)

    deleted = await service.delete_profile(
        tenant_id=tenant,
        profile_id=profile_id
    )

    assert deleted is True