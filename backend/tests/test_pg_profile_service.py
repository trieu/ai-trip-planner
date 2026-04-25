import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.pgsql_service import PostgresProfileService


# ==========================================================
# FIXTURES
# ==========================================================

@pytest.fixture
def service():
    svc = PostgresProfileService()
    svc.engines = [MagicMock()]  # avoid real engine creation
    return svc


@pytest.fixture
def mock_row():
    return {
        "tenant_id": "tenant_1",
        "profile_id": "user_1",
        "first_name": "Thomas"
    }


# ==========================================================
# TEST: CACHE HIT
# ==========================================================

@pytest.mark.asyncio
async def test_get_user_profile_cache_hit(service, mock_row):
    with patch("services.pgsql_service.get_cache") as mock_get_cache:
        mock_get_cache.return_value = json.dumps(mock_row)

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"
        assert result["first_name"] == "Thomas"


# ==========================================================
# TEST: CACHE MISS → DB HIT → CACHE SET
# ==========================================================

@pytest.mark.asyncio
async def test_get_user_profile_db_fetch(service, mock_row):
    mock_conn = AsyncMock()
    mock_result = MagicMock()

    mock_result.mappings.return_value.first.return_value = mock_row
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    service.engines = [mock_engine]

    with patch("services.pgsql_service.get_cache", return_value=None), \
         patch("services.pgsql_service.set_cache_with_ttl") as mock_set_cache:

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"
        mock_set_cache.assert_called_once()


# ==========================================================
# TEST: CACHE CORRUPTED → FALLBACK TO DB
# ==========================================================

@pytest.mark.asyncio
async def test_cache_corrupted(service, mock_row):
    mock_conn = AsyncMock()
    mock_result = MagicMock()

    mock_result.mappings.return_value.first.return_value = mock_row
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    service.engines = [mock_engine]

    with patch("services.pgsql_service.get_cache", return_value="invalid-json"):

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["profile_id"] == "user_1"


# ==========================================================
# TEST: DB RETURNS EMPTY
# ==========================================================

@pytest.mark.asyncio
async def test_no_profile_found(service):
    mock_conn = AsyncMock()
    mock_result = MagicMock()

    mock_result.mappings.return_value.first.return_value = None
    mock_conn.execute.return_value = mock_result

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    service.engines = [mock_engine]

    with patch("services.pgsql_service.get_cache", return_value=None):

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result == {}


# ==========================================================
# TEST: DB ERROR HANDLING
# ==========================================================

@pytest.mark.asyncio
async def test_db_error(service):
    mock_conn = AsyncMock()
    mock_conn.execute.side_effect = Exception("DB down")

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    service.engines = [mock_engine]

    with patch("services.pgsql_service.get_cache", return_value=None):

        result = await service.get_user_profile("tenant_1", "user_1")

        assert result["error"] == "postgres_unavailable"


# ==========================================================
# TEST: CACHE KEY MULTI-TENANT SAFETY
# ==========================================================

def test_cache_key(service):
    key = service._cache_key("tenant_1", "user_1")

    assert key == "profile:tenant_1:user_1"