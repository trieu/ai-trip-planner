import os
import dramatiq
from dramatiq.brokers.redis import RedisBroker
from periodiq import PeriodiqMiddleware
from config import get_settings

DRAMATIQ_REDIS_URL = get_settings().REDIS_URL

# ---------------------------------------------------------
# Dramatiq Broker & Middleware Setup
# ---------------------------------------------------------

# 1. Initialize the Redis Broker
redis_broker = RedisBroker(url=DRAMATIQ_REDIS_URL)

# 2. Add Periodiq middleware for Cron-like scheduling (replaces Celery Beat)
# skip_delay allows Periodiq to skip missed tasks if the worker was down too long.
redis_broker.add_middleware(PeriodiqMiddleware(skip_delay=30))

# 3. Set the global broker so @dramatiq.actor decorators automatically use it
dramatiq.set_broker(redis_broker)

# ---------------------------------------------------------
# Worker Registration
# ---------------------------------------------------------
# Dramatiq needs to discover the actors.
# Importing these modules ensures the @dramatiq.actor decorators are evaluated.
import tasks
import embedding_tasks
