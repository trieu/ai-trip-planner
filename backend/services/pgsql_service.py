from typing import Any, Dict

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from services.data_service import BaseProfileService

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