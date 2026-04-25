import random
import uuid
from datetime import datetime, timedelta
from services.base_service import BaseProfileService
from typing import Dict, Any


# ==========================================
# Mock Data Service (for testing without real dependencies)
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
        self.interests_pool = [
            "beach", "mountains", "culture", "food", "adventure", "relaxation", "nightlife", "history"
        ]

    def _generate_profile(self, user_id: str) -> Dict[str, Any]:
        persona = self.rng.choice(self.personas)

        last_seen = datetime.now() - timedelta(days=self.rng.randint(0, 30))
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
                "last_seen_days_ago": (datetime.now() - last_seen).days,
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
            "personal_interests": self.rng.sample(self.interests_pool, k=3),

            "language": "Vietnamese"
        }

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        self.rng.seed(hash(user_id))
        return self._generate_profile(user_id)
