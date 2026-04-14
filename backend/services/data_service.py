import os
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from sqlalchemy import create_engine, text

class BaseProfileService(ABC):
    """Abstract Base Class for User Profile retrieval."""
    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        pass

class LeoCDPService(BaseProfileService):
    """Implementation for LEO CDP via REST API."""
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        # Implementation for LEO CDP profile lookup
        try:
            with httpx.Client(timeout=5.0) as client:
                # Example LEO CDP endpoint logic
                resp = client.get(
                    f"{self.base_url}/api/v1/profile/{user_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

class PostgresProfileService(BaseProfileService):
    """Implementation for PostgreSQL 16+."""
    def __init__(self, connection_string: str):
        self.engine = create_engine(connection_string)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        query = text("SELECT profile_data FROM user_profiles WHERE user_id = :uid")
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"uid": user_id}).fetchone()
                return result[0] if result else {}
        except Exception:
            return {}

class DataServiceFactory:
    """Factory to instantiate the correct service based on ENV."""
    @staticmethod
    def get_service() -> BaseProfileService:
        source = os.getenv("PROFILE_SOURCE", "LEO_CDP").upper()
        
        if source == "POSTGRES":
            return PostgresProfileService(os.getenv("DATABASE_URL", ""))
        elif source == "LEO_CDP":
            return LeoCDPService(
                api_key=os.getenv("LEO_API_KEY", ""),
                base_url=os.getenv("LEO_BASE_URL", "https://api.leocdp.com")
            )
        else:
            raise ValueError(f"Unsupported profile source: {source}")
