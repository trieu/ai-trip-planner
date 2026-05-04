
# ==========================================
# Base Interface
# ==========================================
from abc import ABC, abstractmethod
import os
from typing import Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from dotenv import load_dotenv

from config import build_pg_dsn, require_env, Settings

# ==========================================
# Load ENV (single source of truth)
# ==========================================
load_dotenv(override=True)

class BaseProfileService(ABC):
    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        pass


def create_engine(dsn: str) -> AsyncEngine:
    """ creates a SQLAlchemy AsyncEngine with connection pooling and pre-ping enabled. 

    Args:
        dsn (str): _description_

    Returns:
        AsyncEngine: _description_
    """
    return create_async_engine(
        dsn,
        pool_size=10,
        max_overflow=20,
        pool_timeout=5,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

def build_engines():
    """ build async engines for PostgreSQL connections, including replicas if configured.

    Returns:
        _type_: _description_
    """
    dns = Settings().PGSQL_DATABASE_DSN
    engines = [create_engine(dns)]

    for i in range(1, 4):
        prefix = f"PGSQL_REPLICA_{i}"
        try:
            if require_env(f"{prefix}_HOST", None):
                engines.append(create_engine(build_pg_dsn(prefix)))
        except Exception:
            continue

    return engines