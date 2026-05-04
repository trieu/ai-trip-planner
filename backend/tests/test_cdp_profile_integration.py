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
# UPSERT UPDATE (same profile_id)
# =====================================================
@pytest.mark.asyncio
async def test_upsert_updates_existing_profile(service, tenant):
    profile_id = str(uuid.uuid4())

    # First insert
    profile_v1 = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=profile_id,
        primary_email="old@example.com",
        first_name="Old",
    )

    await service.upsert_profile(profile_v1)

    # Second upsert (update)
    profile_v2 = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=profile_id,
        primary_email="new@example.com",
        first_name="New",
    )

    await service.upsert_profile(profile_v2)

    result = await service.get_user_profile(tenant, profile_id)

    assert result["primary_email"] == "new@example.com"
    assert result["first_name"] == "New"
    
# =====================================================
# SEARCH MULTIPLE RESULTS
# =====================================================
@pytest.mark.asyncio
async def test_search_multiple_profiles(service, tenant):
    for i in range(3):
        profile = PGProfileUpsert(
            tenant_id=tenant,
            profile_id=str(uuid.uuid4()),
            first_name="SearchUser",
            primary_email=f"user{i}@test.com",
        )
        await service.upsert_profile(profile)

    results = await service.search_profiles(
        tenant_id=tenant,
        keyword="SearchUser"
    )

    assert len(results) >= 3
    
    
# =====================================================
# FILTER BY DATA LABEL
# =====================================================
@pytest.mark.asyncio
async def test_filter_by_data_label(service, tenant):
    profile_vip = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="VIP",
        data_labels=["vip"]
    )

    profile_normal = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="Normal",
        data_labels=["normal"]
    )

    await service.upsert_profile(profile_vip)
    await service.upsert_profile(profile_normal)

    results = await service.filter_profiles(
        tenant_id=tenant,
        filters={"data_label": "vip"}
    )

    assert len(results) == 1
    assert results[0]["first_name"] == "VIP"
    

# =====================================================
# FILTER BY SEGMENT
# =====================================================
@pytest.mark.asyncio
async def test_filter_by_segment(service, tenant):
    profile_segment = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="SegmentUser",
        segments=[{"id": "seg_1", "name": "VIP"}]
    )

    profile_other = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="OtherUser",
        segments=[{"id": "seg_2", "name": "Normal"}]
    )

    await service.upsert_profile(profile_segment)
    await service.upsert_profile(profile_other)

    results = await service.filter_profiles(
        tenant_id=tenant,
        filters={"segment_id": "seg_1"}
    )

    assert len(results) == 1
    assert results[0]["first_name"] == "SegmentUser"
    
# =====================================================
# FILTER BY CITY
# =====================================================
@pytest.mark.asyncio
async def test_filter_by_city(service, tenant):
    profile_hcm = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="HCMUser",
        living_city="HCM"
    )

    profile_hn = PGProfileUpsert(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4()),
        first_name="HNUser",
        living_city="HN"
    )

    await service.upsert_profile(profile_hcm)
    await service.upsert_profile(profile_hn)

    results = await service.filter_profiles(
        tenant_id=tenant,
        filters={"living_city": "HCM"}
    )

    assert len(results) == 1
    assert results[0]["first_name"] == "HCMUser"

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
    
# =====================================================
# DELETE NON-EXISTING
# =====================================================
@pytest.mark.asyncio
async def test_delete_non_existing_profile(service, tenant):
    deleted = await service.delete_profile(
        tenant_id=tenant,
        profile_id=str(uuid.uuid4())
    )

    assert deleted is False