
import dramatiq
from tasks.agent_tasks import generate_trip_plan  # register actor

if __name__ == "__main__":
    print("Starting Dramatiq worker...")