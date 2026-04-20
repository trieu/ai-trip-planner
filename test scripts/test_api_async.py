# test_api_async.py

import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"


async def call_api(client, user_id: str):
    payload = {
        "destination": "Phu Quoc",
        "duration": "5 days",
        "budget": "luxury",
        "interests": "resort, snorkeling",
        "travel_style": "premium",
        "user_id": user_id,
        "session_id": f"session_{user_id}",
        "language": "Vietnamese"
    }

    resp = await client.post("/plan-trip", json=payload)
    return {
        "user_id": user_id,
        "status": resp.status_code,
        "data": resp.json()
    }


async def run_load_test(n=5):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        tasks = [call_api(client, f"user_{i}") for i in range(n)]
        results = await asyncio.gather(*tasks)

        for r in results:
            print(f"\n=== {r['user_id']} ===")
            print("Status:", r["status"])
            print(json.dumps(r["data"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run_load_test(10))