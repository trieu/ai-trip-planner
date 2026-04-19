import os
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

import random
import uuid
from datetime import datetime, timedelta


# ==========================================
# Load ENV (single source of truth)
# ==========================================
load_dotenv()


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required env: {key}")
    return value


# ==========================================
# Base Interface
# ==========================================
class BaseProfileService(ABC):
    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        pass


# ==========================================
# MOCK (deterministic testing)
# ==========================================
class MockProfileService(BaseProfileService):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

        self.personas = [
            {"segment": "high_value", "avg_order_value": 120, "lifetime_value": 5000},
            {"segment": "mid_value", "avg_order_value": 60, "lifetime_value": 1200},
            {"segment": "low_value", "avg_order_value": 20, "lifetime_value": 200},
            {"segment": "churn_risk", "avg_order_value": 45, "lifetime_value": 800},
        ]

        self.cities = ["Ho Chi Minh City", "Hanoi", "Da Nang", "Can Tho"]
        self.channels = ["facebook", "google", "email", "organic"]

    def _generate_profile(self, user_id: str) -> Dict[str, Any]:
        persona = self.rng.choice(self.personas)

        last_seen = datetime.utcnow() - timedelta(days=self.rng.randint(0, 30))
        created_at = last_seen - timedelta(days=self.rng.randint(30, 365))

        return {
            "user_id": user_id,
            "profile_id": str(uuid.uuid4()),
            "segment": persona["segment"],
            "traits": {
                "age": self.rng.randint(18, 55),
                "city": self.rng.choice(self.cities),
                "preferred_channel": self.rng.choice(self.channels),
                "device": self.rng.choice(["mobile", "desktop"]),
            },
            "metrics": {
                "avg_order_value": persona["avg_order_value"],
                "lifetime_value": persona["lifetime_value"],
                "purchase_count": self.rng.randint(1, 50),
                "last_seen_days_ago": (datetime.utcnow() - last_seen).days,
            },
            "timestamps": {
                "created_at": created_at.isoformat(),
                "last_seen": last_seen.isoformat(),
            },
            "consent": {
                "email": self.rng.choice([True, False]),
                "sms": self.rng.choice([True, False]),
                "ads": True,
            },
        }

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        self.rng.seed(hash(user_id))
        return self._generate_profile(user_id)


# ==========================================
# LEO CDP
# ==========================================
class LeoCDPService(BaseProfileService):
    def __init__(self, api_key: str, api_value: str, base_url: str):
        self.api_key = api_key
        self.api_value = api_value
        self.base_url = base_url.rstrip("/")

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.base_url}/api/v1/profile/{user_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "X-API-KEY": self.api_value,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            # log in real system
            return {"error": "leo_cdp_unavailable", "detail": str(e)}


# ==========================================
# POSTGRES
# ==========================================
class PostgresProfileService(BaseProfileService):
    def __init__(self, connection_string: str):
        if not connection_string:
            raise ValueError("DATABASE_URL is required for POSTGRES source")
        self.engine = create_engine(connection_string, pool_pre_ping=True)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        query = text(
            "SELECT profile_data FROM user_profiles WHERE user_id = :uid LIMIT 1"
        )
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {"uid": user_id}).fetchone()
                return dict(result[0]) if result else {}
        except Exception as e:
            return {"error": "postgres_unavailable", "detail": str(e)}


# ==========================================
# Factory (clean + strict)
# ==========================================
class DataServiceFactory:
    @staticmethod
    def get_service() -> BaseProfileService:
        source = os.getenv("PROFILE_SOURCE", "LEO_CDP").upper()

        if source == "POSTGRES":
            return PostgresProfileService(
                require_env("DATABASE_URL")
            )

        elif source == "LEO_CDP":
            return LeoCDPService(
                api_key=require_env("LEO_API_KEY"),
                api_value=require_env("LEO_API_VALUE"),
                base_url=os.getenv("LEO_BASE_URL", "https://api.leocdp.com"),
            )

        elif source == "MOCK_DATA":
            return MockProfileService(
                seed=int(os.getenv("MOCK_SEED", "42"))
            )

        else:
            raise ValueError(f"Unsupported PROFILE_SOURCE: {source}")