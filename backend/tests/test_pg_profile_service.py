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
    svc = PostgresProfileService(db_url=PGSQL_DATABASE_DSN)
    return svc


@pytest.fixture
def mock_row():
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
async def test_cache_corrupted(service, mock_row):
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
    key = service._cache_key("tenant_1", "user_1")
    assert key == "profile:tenant_1:user_1"