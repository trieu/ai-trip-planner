from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
import re
from arango.database import StandardDatabase

# =====================================================
# REGEX & CONSTANTS
# =====================================================
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")

# =====================================================
# EMBEDDED MODELS
# =====================================================
class SegmentRef(BaseModel):
    id: str
    name: Optional[str] = None

class JourneyRef(BaseModel):
    id: str
    name: Optional[str] = None
    funnelIndex: int = 0

class Touchpoint(BaseModel):
    id: str
    hostname: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    parentId: Optional[str] = None

# =====================================================
# MAIN PROFILE MODEL
# =====================================================
class ArangoProfile(BaseModel):
    """
    Read model for profiles loaded from ArangoDB.

    Design rules:
    - Never throw on bad contact data
    - Invalid email / phone → NULL (None)
    - Lists are filtered, not rejected
    - extra fields are ignored safely
    """

    model_config = ConfigDict(
        extra="ignore"   # Silently ignore unexpected fields from the DB
    )

    # =====================================================
    # IDENTITY
    # =====================================================
    profile_id: Optional[str] = None
    identities: List[str] = Field(default_factory=list)

    # =====================================================
    # CONTACT INFORMATION
    # =====================================================
    primaryEmail: Optional[EmailStr] = None
    secondaryEmails: List[EmailStr] = Field(default_factory=list)

    primaryPhone: Optional[str] = None
    secondaryPhones: List[str] = Field(default_factory=list)

    # =====================================================
    # PERSONAL & LOCATION
    # =====================================================
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    livingLocation: Optional[str] = None
    livingCountry: Optional[str] = None
    livingCity: Optional[str] = None

    # =====================================================
    # ENRICHMENT
    # =====================================================
    jobTitles: List[str] = Field(default_factory=list)
    dataLabels: List[str] = Field(default_factory=list)
    contentKeywords: List[str] = Field(default_factory=list)
    mediaChannels: List[str] = Field(default_factory=list)
    behavioralEvents: List[str] = Field(default_factory=list)

    inSegments: List[SegmentRef] = Field(default_factory=list)
    inJourneyMaps: List[JourneyRef] = Field(default_factory=list)

    eventStatistics: Dict[str, int] = Field(default_factory=dict)
    topEngagedTouchpoints: List[Touchpoint] = Field(default_factory=list)

    # =====================================================
    # VALIDATORS (FAIL-SOFT)
    # =====================================================
    @field_validator("primaryEmail", mode="before")
    @classmethod
    def sanitize_primary_email(cls, v):
        if not v:
            return None
        try:
            return EmailStr(v)
        except Exception:
            return None

    @field_validator("secondaryEmails", mode="before")
    @classmethod
    def sanitize_secondary_emails(cls, v):
        if not v:
            return []
        valid: List[str] = []
        for e in v:
            try:
                valid.append(str(EmailStr(e)))
            except Exception:
                continue
        return valid

    @field_validator("primaryPhone", mode="before")
    @classmethod
    def sanitize_primary_phone(cls, v):
        if not v:
            return None
        v = v.strip()
        if _PHONE_RE.match(v):
            return v
        return None

    @field_validator("secondaryPhones", mode="before")
    @classmethod
    def sanitize_secondary_phones(cls, v):
        if not v:
            return []
        return [
            p.strip()
            for p in v
            if isinstance(p, str) and _PHONE_RE.match(p.strip())
        ]

    # =====================================================
    # FACTORY FROM ARANGO DOCUMENT
    # =====================================================
    @classmethod
    def from_arango(cls, doc: Dict[str, Any]) -> "ArangoProfile":
        """
        Build ArangoProfile from raw ArangoDB document dict.
        
        Notes:
        - Validation happens via Pydantic validators.
        - Defaults are handled gracefully to prevent crashes on missing Arango keys.
        """
        return cls(
            # --- identity ---
            profile_id=doc.get("_key"),
            identities=doc.get("identities", []),

            # --- contact ---
            primaryEmail=doc.get("primaryEmail"),
            secondaryEmails=doc.get("secondaryEmails", []),
            primaryPhone=doc.get("primaryPhone"),
            secondaryPhones=doc.get("secondaryPhones", []),

            # --- personal ---
            firstName=doc.get("firstName"),
            lastName=doc.get("lastName"),
            livingLocation=doc.get("livingLocation"),
            livingCountry=doc.get("livingCountry"),
            livingCity=doc.get("livingCity"),

            # --- enrichment ---
            jobTitles=doc.get("jobTitles", []),
            dataLabels=doc.get("dataLabels", []),
            contentKeywords=doc.get("contentKeywords", []),
            mediaChannels=doc.get("mediaChannels", []),
            behavioralEvents=doc.get("behavioralEvents", []),

            # --- segmentation ---
            inSegments=[
                SegmentRef(
                    id=s.get("id", ""), 
                    name=s.get("name")
                )
                for s in doc.get("inSegments", [])
                if isinstance(s, dict)
            ],

            # --- journeys ---
            inJourneyMaps=[
                JourneyRef(
                    id=j.get("id", ""),
                    name=j.get("name"),
                    funnelIndex=j.get("funnelIndex", 0),
                )
                for j in doc.get("inJourneyMaps", [])
                if isinstance(j, dict)
            ],

            # --- statistics ---
            eventStatistics=doc.get("eventStatistics", {}),

            # --- touchpoints ---
            topEngagedTouchpoints=[
                Touchpoint(
                    id=t.get("id", ""),
                    hostname=t.get("hostname"),
                    name=t.get("name"),
                    url=t.get("url"),
                    parentId=t.get("parentId"),
                )
                for t in doc.get("topEngagedTouchpoints", [])
                if isinstance(t, dict)
            ],
        )

# =====================================================
# AQL QUERY
# =====================================================
CDP_PROFILE_QUERY = """
    FOR p IN cdp_profile
        FILTER p.inSegments != null
        FILTER @segment_id IN p.inSegments[*].id
        FILTER (
            (p.primaryEmail != null AND p.primaryEmail != "")
            OR
            (p.primaryPhone != null AND p.primaryPhone != "")
        )

        LET topEngagedTouchpoints = (
            FOR t IN cdp_touchpoint
                FILTER t._key IN p.topEngagedTouchpointIds
                RETURN {
                    id: t._key,
                    hostname: t.hostname,
                    name: t.name,
                    url: t.url,
                    parentId: t.parentId
                }
        )
        
        LIMIT @start_index, @batch_size

        RETURN {
            _key: p._key,
            identities: p.identities,

            primaryEmail: p.primaryEmail,
            secondaryEmails: p.secondaryEmails,

            primaryPhone: p.primaryPhone,
            secondaryPhones: p.secondaryPhones,

            firstName: p.firstName,
            lastName: p.lastName,
            livingLocation: p.livingLocation,
            livingCountry: p.livingCountry,
            livingCity: p.livingCity,

            jobTitles: p.jobTitles,
            dataLabels: p.dataLabels,
            contentKeywords: p.contentKeywords,
            mediaChannels: p.mediaChannels,
            behavioralEvents: p.behavioralEvents,

            inSegments: p.inSegments,
            inJourneyMaps: p.inJourneyMaps,

            eventStatistics: p.eventStatistics,
            topEngagedTouchpoints: topEngagedTouchpoints
        }
"""
