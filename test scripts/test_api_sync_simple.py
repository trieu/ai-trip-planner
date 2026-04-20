# test_api_sync.py

import httpx
import json

BASE_URL = "http://localhost:8000"


def test_plan_trip():
    payload = {
        "destination": "Da Nang",
        "duration": "3 days",
        "budget": "moderate",
        "interests": "beach, food",
        "travel_style": "relaxed",
        "user_id": "user_123",
        "session_id": "test_session_001",
        "language": "Vietnamese"
    }

    try:
        response = httpx.post(f"{BASE_URL}/plan-trip", json=payload, timeout=30.0)

        print(f"Status: {response.status_code}")
        print("Response:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    except Exception as e:
        print("❌ Request failed:", str(e))


if __name__ == "__main__":
    test_plan_trip()