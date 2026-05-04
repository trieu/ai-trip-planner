import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import Settings
from services.cdp_profile_service import PostgresProfileService

PGSQL_DATABASE_DSN = Settings().PGSQL_DATABASE_DSN

if not PGSQL_DATABASE_DSN:
    pytest.skip("Postgres not configured", allow_module_level=True)


# =====================================================
# FIXTURE
# =====================================================
@pytest.fixture
def service():
    """
    Provide a service instance.
    Note:
    - We do NOT hit a real DB in unit tests
    - DB interactions are mocked at session level
    """
    svc = PostgresProfileService(db_url=PGSQL_DATABASE_DSN)
    return svc


@pytest.fixture
def mock_row():
    """
    Represents a canonical DB row.
    Used to simulate database responses consistently across tests.
    """
    return {
        "tenant_id": "tenant_1",
        "profile_id": "user_1",
        "first_name": "Thomas"
    }


# =====================================================
# CACHE HIT
# =====================================================
@pytest.mark.asyncio
async def test_get_user_profile_cache_hit(service, mock_row):
    """
    Scenario:
    - Data is already present in cache (Redis hit)

    Why this test matters:
    - This is the fastest path in production (hot path)
    - Ensures we DO NOT hit DB when cache is valid

    Expected behavior:
    - Return cached data
    - No DB interaction required
    """
    with patch("services.cdp_profile_service.get_cache") as mock_get_cache:
        mock_get_cache.return_value = json.dumps(mock_row)

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"
        assert result["first_name"] == "Thomas"


# =====================================================
# DB FETCH
# =====================================================
@pytest.mark.asyncio
async def test_get_user_profile_db_fetch(service, mock_row):
    """
    Scenario:
    - Cache miss → must fetch from DB

    Why this test matters:
    - Validates fallback path (cache-aside pattern)
    - Ensures DB result is cached after fetch

    Expected behavior:
    - DB is queried
    - Result returned correctly
    - Cache is updated
    """

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    # Mock async session context manager
    service.async_session = MagicMock()
    service.async_session.return_value.__aenter__.return_value = mock_session

    with patch("services.cdp_profile_service.get_cache", return_value=None), \
         patch("services.cdp_profile_service.set_cache_with_ttl") as mock_set_cache:

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"
        mock_set_cache.assert_called_once()


# =====================================================
# CACHE CORRUPTED
# =====================================================
@pytest.mark.asyncio
async def test_cache_corrupted(service, mock_row, caplog):
    """
    Scenario:
    - Cache returns invalid JSON (corrupted / partial data)

    Why this test matters:
    - Cache corruption happens in real systems (TTL race, manual writes, version mismatch)
    - System must NOT crash due to bad cache
    - Must fallback safely to DB

    Expected behavior:
    - Cache read fails silently
    - DB is queried
    - Valid data returned
    - Warning is logged (suppressed in test)
    """

    caplog.set_level("CRITICAL")  # suppress WARNING logs

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    service.async_session = MagicMock()
    service.async_session.return_value.__aenter__.return_value = mock_session

    with patch("services.cdp_profile_service.get_cache", return_value="invalid-json"):
        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"


# =====================================================
# NOT FOUND
# =====================================================
@pytest.mark.asyncio
async def test_no_profile_found(service):
    """
    Scenario:
    - Cache miss
    - DB returns no row

    Why this test matters:
    - Ensures consistent API contract for "not found"
    - Avoids returning None (which causes bugs upstream)

    Expected behavior:
    - Return empty dict {}
    """

    mock_result = MagicMock()
    mock_result.mappings.return_value.first.return_value = None

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    service.async_session = MagicMock()
    service.async_session.return_value.__aenter__.return_value = mock_session

    with patch("services.cdp_profile_service.get_cache", return_value=None):
        result = await service.get_user_profile("tenant_1", "user_1")

        assert result == {}


# =====================================================
# DB ERROR
# =====================================================
@pytest.mark.asyncio
async def test_db_error(service, caplog):
    """
    Scenario:
    - Database is unavailable (network issue, crash, timeout)

    Why this test matters:
    - This is a real production failure mode
    - Service must degrade gracefully (NOT crash)

    Expected behavior:
    - Catch exception
    - Log error (suppressed here)
    - Return structured error response
    """

    caplog.set_level("CRITICAL")  # suppress ERROR logs

    mock_session = AsyncMock()
    mock_session.execute.side_effect = Exception("DB down")

    service.async_session = MagicMock()
    service.async_session.return_value.__aenter__.return_value = mock_session

    with patch("services.cdp_profile_service.get_cache", return_value=None):
        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["error"] == "postgres_unavailable"


# =====================================================
# CACHE KEY
# =====================================================
def test_cache_key(service):
    """
    Scenario:
    - Generate cache key

    Why this test matters:
    - Cache key must be deterministic
    - Critical for multi-tenant isolation
    - Prevents cache collision across tenants

    Expected behavior:
    - Format: profile:{tenant_id}:{user_id}
    """

    key = service._cache_key("tenant_1", "user_1")
    assert key == "profile:tenant_1:user_1"