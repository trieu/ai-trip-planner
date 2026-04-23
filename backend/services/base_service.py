
# ==========================================
# Base Interface
# ==========================================
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseProfileService(ABC):
    @abstractmethod
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        pass
