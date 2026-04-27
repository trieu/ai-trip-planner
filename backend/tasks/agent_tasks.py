import dramatiq
import time

# Redis broker (default localhost:6379)
from dramatiq.brokers.redis import RedisBroker

redis_broker = RedisBroker(host="localhost", port=6379)
dramatiq.set_broker(redis_broker)

def save_plan_to_db(plan):
    # TODO: Implement actual DB persistence (PostgreSQL, CDP, etc.)
    print(f"[Agent] Saved plan for user={plan['user_id']} to DB: {plan['destination']} with itinerary {plan['itinerary']}")


@dramatiq.actor(max_retries=3, time_limit=60000)
def generate_trip_plan(user_id: str, destination: str):
    print(f"[Agent] Planning trip for user={user_id} to {destination}")

    time.sleep(2)

    plan = {
        "user_id": user_id,
        "destination": destination,
        "itinerary": [
            "Day 1: Arrival + city tour",
            "Day 2: Local food + attractions",
            "Day 3: Relax + shopping"
        ]
    }

    # ✅ Persist to DB (Postgres / CDP)
    save_plan_to_db(plan)