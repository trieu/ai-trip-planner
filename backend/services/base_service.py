
# ==========================================
# Base Interface
# ==========================================
from abc import ABC, abstractmethod
import os
from typing import Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from dotenv import load_dotenv

# ==========================================
# Load ENV (single source of truth)
# ==========================================
load_dotenv(override=True)

class BaseProfileService(ABC):
    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        pass

# Utility function to ensure required env variables are present
def require_env(key: str, default_value : str = None) -> str:
    '''Get an environment variable or raise an error if it's missing.'''
    value = os.getenv(key)
    if not value:
        if default_value is not None:
            return default_value
        raise ValueError(f"Missing required env: {key}")
    return value


def build_pg_dsn(prefix: str = "PGSQL_DB") -> str:
    return (
        f"postgresql+asyncpg://"
        f"{require_env(f'{prefix}_USER')}:"
        f"{require_env(f'{prefix}_PASSWORD')}@"
        f"{require_env(f'{prefix}_HOST', 'localhost')}:"
        f"{require_env(f'{prefix}_PORT', '5432')}/"
        f"{require_env(f'{prefix}_NAME')}"
    )


def create_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=10,
        max_overflow=20,
        pool_timeout=5,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

def build_engines():
    engines = [create_engine(build_pg_dsn())]

    for i in range(1, 4):
        prefix = f"PGSQL_REPLICA_{i}"
        try:
            if require_env(f"{prefix}_HOST", None):
                engines.append(create_engine(build_pg_dsn(prefix)))
        except Exception:
            continue

    return engines