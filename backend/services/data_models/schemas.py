from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ================================
# Trip Planning Models (Existing)
# ================================

# ================================
# Data Models (Pydantic)
# ================================
class TripRequest(BaseModel):
    """Schema for incoming trip planning requests."""
    destination: str
    duration: Optional[str] = "3 days"
    budget: Optional[str] = "moderate"
    interests: Optional[str] = None
    travel_style: Optional[str] = None
    user_input: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    turn_index: Optional[int] = 0

class TripResponse(BaseModel):
    """Schema for successful trip plan responses."""
    result: str
    tool_calls: List[Dict[str, Any]] = []


# ================================
# Persona Report Models
# ================================

class SocialMediaSignal(BaseModel):
    """A single social media listening signal."""
    title: str = Field(..., description="Signal title")
    value: str = Field(..., description="Signal value or description")
    sentiment: Optional[str] = Field(None, description="Sentiment: positive, neutral, negative")
    icon: Optional[str] = Field(None, description="Bootstrap icon class")
    badge: Optional[str] = Field(None, description="Badge type: positive, neutral, negative")


class FirstPartyDataSignal(BaseModel):
    """A single first-party data signal."""
    title: str = Field(..., description="Signal title")
    value: str = Field(..., description="Signal value or description")
    metric: Optional[str] = Field(None, description="Metric type")
    icon: Optional[str] = Field(None, description="Bootstrap icon class")
    badge: Optional[str] = Field(None, description="Badge type")


class MarketResearchSignal(BaseModel):
    """A single market research insight."""
    title: str = Field(..., description="Insight title")
    value: str = Field(..., description="Insight value or description")
    type: Optional[str] = Field(None, description="Insight type: opportunity, threat, trend")
    icon: Optional[str] = Field(None, description="Bootstrap icon class")
    badge: Optional[str] = Field(None, description="Badge type")


class DataSourceMetrics(BaseModel):
    """Metrics summary for a data source."""
    total_signals: int = Field(..., description="Total number of signals")
    last_updated: str = Field(..., description="Last update timestamp")
    coverage: str = Field(..., description="Data coverage area")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")


class PersonaDataSource(BaseModel):
    """Complete data source with all signals."""
    source_type: str = Field(..., description="Type: social_media, first_party, market_research")
    title: str = Field(..., description="Source title")
    description: str = Field(..., description="Source description")
    icon: str = Field(..., description="Bootstrap icon class")
    color: str = Field(..., description="Color code: social, firstparty, market")
    signals: List[Dict[str, Any]] = Field(..., description="List of signals")
    metrics: DataSourceMetrics = Field(..., description="Source metrics")
    stats: Dict[str, str] = Field(default_factory=dict, description="Additional stats")


class JourneyStage(BaseModel):
    """A single stage in the customer journey."""
    stage_id: int = Field(..., description="Stage identifier 0-4")
    title: str = Field(..., description="Stage title")
    description: str = Field(..., description="Stage description")
    persona_score: float = Field(..., ge=0, le=1, description="Persona score at this stage")
    sentiment: str = Field(..., description="Sentiment: positive, neutral, negative")
    recommendations: List[Dict[str, str]] = Field(..., description="Recommended actions")


class PersonaTrait(BaseModel):
    """A persona trait with score."""
    name: str = Field(..., description="Trait name")
    score: float = Field(..., ge=0, le=100, description="Trait score 0-100")
    description: Optional[str] = Field(None, description="Trait description")


class CustomerPersona(BaseModel):
    """Complete customer persona definition."""
    persona_id: str = Field(..., description="Unique persona ID")
    name: str = Field(..., description="Persona name")
    description: str = Field(..., description="Persona description")
    avatar: Optional[str] = Field(None, description="Avatar URL or base64")
    key_behaviors: List[str] = Field(..., description="Key behaviors list")
    traits: List[PersonaTrait] = Field(..., description="Persona traits with scores")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")


class SentimentData(BaseModel):
    """Sentiment distribution data."""
    positive: int = Field(..., ge=0, description="Positive mentions count")
    neutral: int = Field(..., ge=0, description="Neutral mentions count")
    negative: int = Field(..., ge=0, description="Negative mentions count")
    last_updated: str = Field(..., description="Last update timestamp")
    window_minutes: int = Field(default=60, description="Time window in minutes")


class PersonaReport(BaseModel):
    """Complete customer persona report."""
    report_id: str = Field(..., description="Unique report ID")
    customer_id: Optional[str] = Field(None, description="Associated customer ID")
    persona: CustomerPersona = Field(..., description="Customer persona")
    social_media_source: PersonaDataSource = Field(..., description="Social media listening data")
    first_party_source: PersonaDataSource = Field(..., description="First-party data source")
    market_research_source: PersonaDataSource = Field(..., description="Market research data")
    journey_stages: List[JourneyStage] = Field(..., description="Customer journey stages")
    sentiment: SentimentData = Field(..., description="Overall sentiment data")
    insights: List[str] = Field(default_factory=list, description="Key insights")
    recommendations: List[str] = Field(default_factory=list, description="Strategic recommendations")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation time")
    version: str = Field(default="1.0", description="Report schema version")


class PersonaReportRequest(BaseModel):
    """Request to generate or fetch a persona report."""
    customer_id: Optional[str] = Field(None, description="Customer ID to generate report for")
    persona_id: Optional[str] = Field(None, description="Specific persona to use")
    include_sentiment: bool = Field(default=True, description="Include sentiment analysis")
    include_recommendations: bool = Field(default=True, description="Include recommendations")
    data_sources: Optional[List[str]] = Field(
        default=["social_media", "first_party", "market_research"],
        description="Data sources to include"
    )


class PersonaReportResponse(BaseModel):
    """Response containing the generated persona report."""
    success: bool = Field(..., description="Whether generation was successful")
    report: Optional[PersonaReport] = Field(None, description="Generated report")
    error: Optional[str] = Field(None, description="Error message if failed")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Response generation time")
