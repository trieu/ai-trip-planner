"""
Data model for PostgreSQL CDP profile upsert operations.
The model is mapped to the structure of the cdp_profiles table and Arango CDP profile data.
"""

from __future__ import annotations
import re
import uuid
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, EmailStr, Field, field_validator, TypeAdapter
from psycopg.types.json import Json

# ---------------------------------------------------------------------
# Constants & Helpers
# ---------------------------------------------------------------------

logger = logging.getLogger(__name__)
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")
_email_adapter = TypeAdapter(EmailStr)

class PGProfileUpsert(BaseModel):
    """
    Data model for upserting a CDP profile into PostgreSQL.
    
    Fixes:
    - tenant_id now accepts UUID objects to prevent Pydantic validation errors.
    - Validators properly catch exceptions to maintain "fail-soft" behavior.
    """

    # =====================================================
    # MULTI-TENANCY
    # =====================================================
    # Use Union to allow both the UUID object and string representations
    tenant_id: Union[uuid.UUID, str]

    # =====================================================
    # CORE IDENTITY
    # =====================================================
    profile_id: str
    identities: List[str] = Field(default_factory=list)

    # =====================================================
    # CONTACT INFORMATION
    # =====================================================
    primary_email: Optional[str] = None # Change to str to allow fail-soft bypass
    secondary_emails: List[str] = Field(default_factory=list)

    primary_phone: Optional[str] = None
    secondary_phones: List[str] = Field(default_factory=list)

    # =====================================================
    # PERSONAL & LOCATION
    # =====================================================
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    living_location: Optional[str] = None
    living_country: Optional[str] = None
    living_city: Optional[str] = None

    # =====================================================
    # ENRICHMENT & INTEREST SIGNALS
    # =====================================================
    job_titles: List[str] = Field(default_factory=list)
    data_labels: List[str] = Field(default_factory=list)
    content_keywords: List[str] = Field(default_factory=list)
    media_channels: List[str] = Field(default_factory=list)
    behavioral_events: List[str] = Field(default_factory=list)

    # =====================================================
    # SEGMENTATION & JOURNEYS
    # =====================================================
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    journey_maps: List[Dict[str, Any]] = Field(default_factory=list)

    # =====================================================
    # STATISTICS & TOUCHPOINTS
    # =====================================================
    event_statistics: Dict[str, int] = Field(default_factory=dict)
    top_engaged_touchpoints: List[Dict[str, Any]] = Field(default_factory=list)

    # =====================================================
    # EXTENSIBILITY
    # =====================================================
    ext_data: Dict[str, Any] = Field(default_factory=dict)

    # =====================================================
    # VALIDATORS (FAIL-SOFT)
    # =====================================================

    @field_validator("tenant_id", mode="before")
    @classmethod
    def ensure_tenant_id_str(cls, v):
        """Coerce UUID to string if necessary."""
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    @field_validator("primary_email", mode="before")
    @classmethod
    def normalize_primary_email(cls, v):
        if not v:
            return None
        try:
            # Validate using EmailStr logic but return as plain string
            return str(_email_adapter.validate_python(v))
        except Exception:
            logger.warning("Invalid primary email dropped: %s", v)
            return None

    @field_validator("secondary_emails", mode="before")
    @classmethod
    def normalize_secondary_emails(cls, v):
        if not v or not isinstance(v, list):
            return []
        valid: List[str] = []
        for e in v:
            try:
                valid.append(str(_email_adapter.validate_python(e)))
            except Exception:
                continue
        return valid

    @field_validator("primary_phone", mode="before")
    @classmethod
    def normalize_primary_phone(cls, v):
        if not v:
            return None
        s_v = str(v).strip()
        return s_v if _PHONE_RE.match(s_v) else None

    @field_validator("secondary_phones", mode="before")
    @classmethod
    def normalize_secondary_phones(cls, v):
        if not v or not isinstance(v, list):
            return []
        return [str(p).strip() for p in v if _PHONE_RE.match(str(p).strip())]

    # =====================================================
    # SERIALIZATION FOR POSTGRES
    # =====================================================
    def to_pg_row(self) -> Dict[str, Any]:
        """
        Convert to a dict compatible with psycopg.
        """
        # Ensure tenant_id is string for the SQL parameter if needed, 
        # though psycopg3 handles UUID objects.
        t_id = str(self.tenant_id)

        return {
            "tenant_id": t_id,
            "profile_id": self.profile_id,
            "identities": Json(self.identities),
            "primary_email": self.primary_email,
            "secondary_emails": Json(self.secondary_emails),
            "primary_phone": self.primary_phone,
            "secondary_phones": Json(self.secondary_phones),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "living_location": self.living_location,
            "living_country": self.living_country,
            "living_city": self.living_city,
            "job_titles": Json(self.job_titles),
            "data_labels": Json(self.data_labels),
            "content_keywords": Json(self.content_keywords),
            "media_channels": Json(self.media_channels),
            "behavioral_events": Json(self.behavioral_events),
            "segments": Json(self.segments),
            "journey_maps": Json(self.journey_maps),
            "event_statistics": Json(self.event_statistics),
            "top_engaged_touchpoints": Json(self.top_engaged_touchpoints),
            "ext_data": Json(self.ext_data),
        }