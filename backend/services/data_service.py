import os

from services.base_service import BaseProfileService, require_env
from services.leocdp_service import LeoCDPService
from services.pgsql_service import PostgresProfileService
from services.mock_test_service import MockProfileService


# ==========================================
# Factory (clean + strict)
# ==========================================
class DataServiceFactory:
    '''Factory class to create instances of data services based on environment configuration.'''
    
    @staticmethod
    def get_service() -> BaseProfileService:
        '''Factory method to get the appropriate data service based on environment configuration.'''
        
        # Determine the data source from environment variables
        source = os.getenv("PROFILE_SOURCE", "LEO_CDP").upper()

        # In a real system, we might also want to support multiple sources at once, with fallback logic.
        
        if source == "POSTGRES":
            # PGSQL connection string should be in the form: postgresql://user:password@host:port/dbname
            return PostgresProfileService(
                require_env("DATABASE_URL")
            )

        elif source == "LEO_CDP":
            # LEO CDP requires an API key and value, which should be set in the environment variables
            return LeoCDPService(
                api_key=require_env("LEO_API_KEY"),
                api_value=require_env("LEO_API_VALUE"),
                base_url=os.getenv("LEO_BASE_URL", "https://api.leocdp.com"),
            )

        elif source == "MOCK_DATA":
            # For testing purposes, we can return a mock service that generates fake profiles
            return MockProfileService(
                seed=int(os.getenv("MOCK_SEED", "42"))
            )

        else:
            raise ValueError(f"Unsupported PROFILE_SOURCE: {source}")
