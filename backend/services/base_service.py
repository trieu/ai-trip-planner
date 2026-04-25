
# ==========================================
# Base Interface
# ==========================================
from abc import ABC, abstractmethod
import os
from typing import Dict, Any

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