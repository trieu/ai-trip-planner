from __future__ import annotations
import re
import uuid
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, EmailStr, Field, field_validator, TypeAdapter
import json

# ---------------------------------------------------------------------
# Constants & Helpers
# ---------------------------------------------------------------------

logger = logging.getLogger(__name__)
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
_email_adapter = TypeAdapter(EmailStr)


class PGProfileUpsert(BaseModel):

    tenant_id: Union[uuid.UUID, str]
    profile_id: str
    identities: List[str] = Field(default_factory=list)

    primary_email: Optional[str] = None
    secondary_emails: List[str] = Field(default_factory=list)

    primary_phone: Optional[str] = None
    secondary_phones: List[str] = Field(default_factory=list)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    living_location: Optional[str] = None
    living_country: Optional[str] = None
    living_city: Optional[str] = None

    job_titles: List[str] = Field(default_factory=list)
    data_labels: List[str] = Field(default_factory=list)
    content_keywords: List[str] = Field(default_factory=list)
    media_channels: List[str] = Field(default_factory=list)
    behavioral_events: List[str] = Field(default_factory=list)

    segments: List[Dict[str, Any]] = Field(default_factory=list)
    journey_maps: List[Dict[str, Any]] = Field(default_factory=list)

    event_statistics: Dict[str, int] = Field(default_factory=dict)
    top_engaged_touchpoints: List[Dict[str, Any]] = Field(default_factory=list)

    ext_data: Dict[str, Any] = Field(default_factory=dict)

    # ================= VALIDATORS =================

    @field_validator("tenant_id", mode="before")
    @classmethod
    def ensure_tenant_id_str(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("primary_email", mode="before")
    @classmethod
    def normalize_primary_email(cls, v):
        if not v:
            return None
        try:
            return str(_email_adapter.validate_python(v))
        except Exception:
            logger.warning("Invalid primary email dropped: %s", v)
            return None

    @field_validator("secondary_emails", mode="before")
    @classmethod
    def normalize_secondary_emails(cls, v):
        if not isinstance(v, list):
            return []
        return [str(_email_adapter.validate_python(e)) for e in v if e]

    @field_validator("primary_phone", mode="before")
    @classmethod
    def normalize_primary_phone(cls, v):
        if not v:
            return None
        v = str(v).strip()
        return v if _PHONE_RE.match(v) else None

    @field_validator("secondary_phones", mode="before")
    @classmethod
    def normalize_secondary_phones(cls, v):
        if not isinstance(v, list):
            return []
        return [str(p).strip() for p in v if _PHONE_RE.match(str(p).strip())]

    # ================= SERIALIZATION =================

    def to_pg_row(self) -> Dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "profile_id": self.profile_id,

            # 🔥 CRITICAL FIX
            "identities": json.dumps(self.identities),
            "secondary_emails": json.dumps(self.secondary_emails),
            "secondary_phones": json.dumps(self.secondary_phones),
            "job_titles": json.dumps(self.job_titles),
            "data_labels": json.dumps(self.data_labels),
            "content_keywords": json.dumps(self.content_keywords),
            "media_channels": json.dumps(self.media_channels),
            "behavioral_events": json.dumps(self.behavioral_events),
            "segments": json.dumps(self.segments),
            "journey_maps": json.dumps(self.journey_maps),
            "event_statistics": json.dumps(self.event_statistics),
            "top_engaged_touchpoints": json.dumps(self.top_engaged_touchpoints),
            "ext_data": json.dumps(self.ext_data),

            # normal fields
            "primary_email": self.primary_email,
            "primary_phone": self.primary_phone,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "living_location": self.living_location,
            "living_country": self.living_country,
            "living_city": self.living_city,
        }