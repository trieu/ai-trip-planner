
# ==========================================
# LEO CDP
# ==========================================
from typing import Any, Dict

import httpx

from services.data_service import BaseProfileService


class LeoCDPService(BaseProfileService):
    def __init__(self, api_key: str, api_value: str, base_url: str):
        self.api_key = api_key
        self.api_value = api_value
        self.base_url = base_url.rstrip("/")

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.base_url}/api/v1/profile/{user_id}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "X-API-KEY": self.api_value,
                    },
                )
                # 
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            # log in real system
            return {"error": "leo_cdp_unavailable", "detail": str(e)}
