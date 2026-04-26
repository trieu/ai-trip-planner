import json
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from data_models.schemas import (
    PersonaReport,
    PersonaReportRequest,
    PersonaReportResponse,
    CustomerPersona,
    PersonaDataSource,
    JourneyStage,
    SentimentData,
    PersonaTrait,
    DataSourceMetrics,
)
from core.config import DATA_DIR, REPORT_TEMPLATE_DIR


class PersonaService:
    """
    Service for loading, generating, and managing customer persona reports.
    Handles JSON data loading and report construction.
    """

    def __init__(self):
        """Initialize the service and ensure data directories exist."""
        self.data_dir = DATA_DIR
        self.template_dir = REPORT_TEMPLATE_DIR
        self._ensure_directories()
        self.report_cache: Dict[str, PersonaReport] = {}

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.template_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "personas"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "reports"), exist_ok=True)

    def load_json(self, file_path: str) -> Dict[str, Any]:
        """
        Load JSON data from file.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON data as dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"JSON file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Invalid JSON in {file_path}: {str(e)}", e.doc, e.pos)

    def save_json(self, file_path: str, data: Dict[str, Any]) -> None:
        """
        Save data to JSON file.

        Args:
            file_path: Path where to save JSON
            data: Data to save
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_persona(self, persona_id: str) -> Optional[CustomerPersona]:
        """
        Load a persona definition from JSON file.

        Args:
            persona_id: Persona identifier

        Returns:
            CustomerPersona object or None if not found
        """
        file_path = os.path.join(self.data_dir, "personas", f"{persona_id}.json")

        try:
            data = self.load_json(file_path)
            return CustomerPersona(**data)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"Error loading persona {persona_id}: {str(e)}")
            return None

    def load_data_source(self, source_type: str, data: Dict[str, Any]) -> PersonaDataSource:
        """
        Load a data source from dictionary.

        Args:
            source_type: Type of source (social_media, first_party, market_research)
            data: Source data dictionary

        Returns:
            PersonaDataSource object
        """
        # Set default metrics if not provided
        if "metrics" not in data:
            data["metrics"] = {
                "total_signals": len(data.get("signals", [])),
                "last_updated": datetime.utcnow().isoformat(),
                "coverage": "Vietnam",
                "confidence": 0.85,
            }

        return PersonaDataSource(
            source_type=source_type,
            title=data.get("title", ""),
            description=data.get("description", ""),
            icon=data.get("icon", ""),
            color=data.get("color", ""),
            signals=data.get("signals", []),
            metrics=DataSourceMetrics(**data.get("metrics", {})),
            stats=data.get("stats", {}),
        )

    def load_journey_stages(self, data: List[Dict[str, Any]]) -> List[JourneyStage]:
        """
        Load journey stages from list of dictionaries.

        Args:
            data: List of stage dictionaries

        Returns:
            List of JourneyStage objects
        """
        stages = []
        for idx, stage_data in enumerate(data):
            stage = JourneyStage(
                stage_id=idx,
                title=stage_data.get("title", ""),
                description=stage_data.get("description", ""),
                persona_score=stage_data.get("persona_score", 0.5),
                sentiment=stage_data.get("sentiment", "neutral"),
                recommendations=stage_data.get("recommendations", []),
            )
            stages.append(stage)
        return stages

    def load_sample_report(self) -> Dict[str, Any]:
        """
        Load sample data for demonstration.
        This returns hardcoded sample data if JSON files don't exist.

        Returns:
            Dictionary with sample report data
        """
        return {
            "persona": {
                "name": "Budget Traveler",
                "description": "Price-conscious last-minute booker with strong social media presence",
                "key_behaviors": [
                    "High price sensitivity & coupon usage",
                    "Last-minute booking patterns",
                    "Social complaint detection",
                    "Likely to share experience on social media",
                ],
                "traits": [
                    {"name": "Price Sensitivity", "score": 90, "description": "Highly sensitive to pricing"},
                    {"name": "Booking Predictability", "score": 65, "description": "Moderately predictable booking times"},
                    {"name": "Complaint Risk", "score": 78, "description": "Higher risk of complaints"},
                    {"name": "Social Influence", "score": 72, "description": "Strong social media influence"},
                ],
            },
            "social_media_source": {
                "title": "Social Media Listening",
                "description": "Real-time monitoring of customer sentiment and engagement across social channels",
                "icon": "bi bi-chat-dots-fill",
                "color": "social",
                "signals": [
                    {
                        "title": "Complaint Mentions",
                        "value": "TikTok: Flight delay complaint 2h ago · 8.2K impressions · 1.2K profile clicks",
                        "sentiment": "negative",
                        "badge": "negative",
                    },
                    {
                        "title": "Sentiment Score",
                        "value": "-0.45 (negative trend, 12% increase in complaints over last 24h)",
                        "sentiment": "negative",
                        "badge": "negative",
                    },
                    {
                        "title": "Engagement Rate",
                        "value": "142 likes, 28 shares, 5 replies · Post is gaining viral momentum · High engagement",
                        "sentiment": "positive",
                        "badge": "positive",
                    },
                    {
                        "title": "Topics & Hashtags",
                        "value": "#cheapflights · #vietjet · #travelfail · #budget · #traveldiscount",
                    },
                    {
                        "title": "Reach & Impressions",
                        "value": "8.2K impressions (last 24h) · 1.2K profile clicks · 420 new followers from this post",
                    },
                ],
                "metrics": {
                    "total_signals": 5,
                    "last_updated": datetime.utcnow().isoformat(),
                    "coverage": "Vietnam",
                    "confidence": 0.85,
                },
                "stats": {
                    "monitoring_window": "Last 24h",
                    "region": "Vietnam",
                    "channels": "4",
                },
            },
            "first_party_source": {
                "title": "First-Party Data",
                "description": "Direct customer behavior, transactions, and engagement data from your platforms",
                "icon": "bi bi-people-fill",
                "color": "firstparty",
                "signals": [
                    {
                        "title": "Booking Behavior",
                        "value": "6 bookings in 30 days · Average spend: $156 · Consistent last-minute booker · No advance planning",
                        "badge": "positive",
                    },
                    {
                        "title": "Price Sensitivity",
                        "value": "Uses price filters on 90% of searches · Applies coupons on 78% of purchases · Always looks for discounts",
                        "badge": "negative",
                    },
                    {
                        "title": "Booking Frequency",
                        "value": "2-3 bookings per month · Zero refunds · Budget-conscious travel style · Sticks with purchases",
                        "badge": "positive",
                    },
                    {
                        "title": "Customer Lifetime Value",
                        "value": "CLV: $2,340 · Retention rate: 65% · Churn risk: Medium · High profit margin customer",
                    },
                    {
                        "title": "Device & Channel Preference",
                        "value": "Mobile: 85% of interactions · iOS app preferred · Push notification open rate: 42% · Email engagement: High",
                    },
                ],
                "metrics": {
                    "total_signals": 5,
                    "last_updated": datetime.utcnow().isoformat(),
                    "coverage": "Vietnam",
                    "confidence": 0.90,
                },
                "stats": {
                    "last_visit": "6h ago",
                    "emails_opened": "5 of 7",
                    "engagement": "High",
                },
            },
            "market_research_source": {
                "title": "Market Research & Competitive Intel",
                "description": "Industry trends, competitive benchmarking, and market opportunities analysis",
                "icon": "bi bi-graph-up-arrow",
                "color": "market",
                "signals": [
                    {
                        "title": "Competitor Benchmarking",
                        "value": "Bamboo Airways: 15% cheaper pricing · AirAsia: Better service ratings · Vietjet leads in budget segment",
                        "badge": "neutral",
                    },
                    {
                        "title": "Review Aggregation & Ratings",
                        "value": "Vietjet average rating: 3.8/5 stars · Common complaints: Service delays, hidden baggage fees",
                        "badge": "negative",
                    },
                    {
                        "title": "Industry Trends & Growth",
                        "value": "Budget travel segment: +12% YoY growth · Online booking penetration: 78% · Mobile-first bookings growing 23%",
                        "badge": "positive",
                    },
                    {
                        "title": "Customer Support Sentiment Analysis",
                        "value": "Response rate: 68% (below industry standard 85%) · Satisfaction score: 62%",
                        "badge": "negative",
                    },
                    {
                        "title": "Market Opportunity & Strategic Insights",
                        "value": "Improve service quality to compete with Bamboo Airways · Free baggage inclusion could be key differentiator",
                    },
                ],
                "metrics": {
                    "total_signals": 5,
                    "last_updated": datetime.utcnow().isoformat(),
                    "coverage": "Vietnam",
                    "confidence": 0.80,
                },
                "stats": {
                    "data_updated": "Today",
                    "competitors_tracked": "12",
                    "reviews_analyzed": "2.3K+",
                },
            },
            "journey_stages": [
                {
                    "title": "Social Listening",
                    "description": "User complains on TikTok about flight delay — sentiment negative, opportunity to retain.",
                    "persona_score": 0.6,
                    "sentiment": "negative",
                    "recommendations": [
                        {"title": "Service Recovery", "desc": "20% flight voucher + priority rebooking", "channels": "DM, Email"},
                        {"title": "Issue Escalation", "desc": "Route to VIP support team immediately", "channels": "System"},
                        {"title": "Sentiment Monitor", "desc": "Track follow-up mentions over next 24h", "channels": "Dashboard"},
                    ],
                },
                {
                    "title": "Search",
                    "description": "User searches for cheaper alternatives and dates. High price sensitivity signals evident.",
                    "persona_score": 0.7,
                    "sentiment": "neutral",
                    "recommendations": [
                        {"title": "Flash Sale Push", "desc": "Limited-time offer on app home screen", "channels": "App Push"},
                        {"title": "Dynamic Retargeting", "desc": "Show similar routes at 15% discount", "channels": "Facebook, Google"},
                        {"title": "Cart Reminder", "desc": "Email with best price guarantee + coupon code", "channels": "Email"},
                    ],
                },
                {
                    "title": "Compare",
                    "description": "Comparing carriers and fares; coupon use probability increases significantly.",
                    "persona_score": 0.8,
                    "sentiment": "neutral",
                    "recommendations": [
                        {"title": "Price Match", "desc": "Guarantee lower price than competitors", "channels": "Website"},
                        {"title": "Social Proof", "desc": "Show 4.8★ reviews from similar travelers", "channels": "Comparison Page"},
                        {"title": "Limited Time", "desc": "Countdown timer: 2 seats at this price", "channels": "Web, App"},
                    ],
                },
                {
                    "title": "Purchase",
                    "description": "Booking VietJet flight at discounted price with applied coupon code. Conversion confirmed.",
                    "persona_score": 0.9,
                    "sentiment": "positive",
                    "recommendations": [
                        {"title": "Confirmation & Upsell", "desc": "Travel insurance & seat upgrade offers", "channels": "Email"},
                        {"title": "Pre-Trip Engagement", "desc": "Packing tips, destination guides 48h before", "channels": "App, Email"},
                        {"title": "Loyalty Bonus", "desc": "+2x points for this booking (limited offer)", "channels": "App"},
                    ],
                },
                {
                    "title": "Experience & Advocacy",
                    "description": "Shares positive experience on Facebook and tags friends. Strong advocate signals detected.",
                    "persona_score": 0.75,
                    "sentiment": "positive",
                    "recommendations": [
                        {"title": "Referral Incentive", "desc": "$50 credit for each friend who books", "channels": "Email, App"},
                        {"title": "UGC Amplify", "desc": "Repost user content on brand channels", "channels": "Social"},
                        {"title": "VIP Program", "desc": "Invite to exclusive frequent flyer benefits", "channels": "Email"},
                    ],
                },
            ],
            "sentiment": {
                "positive": 12,
                "neutral": 8,
                "negative": 5,
                "last_updated": datetime.utcnow().isoformat(),
                "window_minutes": 60,
            },
            "insights": [
                "High complaint risk detected. Recommend immediate engagement with service recovery offer.",
                "Customer shows strong price sensitivity (90%) and last-minute booking patterns.",
                "Social media presence is significant with viral potential in budget travel segment.",
            ],
            "recommendations": [
                "Implement proactive service recovery for negative sentiment mentions.",
                "Create dynamic pricing offers for last-minute bookings to capture sales.",
                "Develop referral program to leverage strong social advocacy signals.",
            ],
        }

    def generate_report(
        self,
        request: PersonaReportRequest,
        report_data: Optional[Dict[str, Any]] = None,
    ) -> PersonaReportResponse:
        """
        Generate a complete persona report.

        Args:
            request: PersonaReportRequest with report parameters
            report_data: Optional pre-loaded report data (defaults to sample if None)

        Returns:
            PersonaReportResponse with generated report or error
        """
        try:
            # Load sample data if not provided
            if report_data is None:
                report_data = self.load_sample_report()

            # Generate unique report ID
            report_id = str(uuid.uuid4())

            # Build persona
            persona_data = report_data.get("persona", {})
            persona_data["persona_id"] = f"persona_{request.persona_id or 'default'}"
            persona = CustomerPersona(**persona_data)

            # Build data sources
            social_media = self.load_data_source(
                "social_media", report_data.get("social_media_source", {})
            )
            first_party = self.load_data_source(
                "first_party", report_data.get("first_party_source", {})
            )
            market = self.load_data_source(
                "market_research", report_data.get("market_research_source", {})
            )

            # Build journey stages
            journey_stages = self.load_journey_stages(report_data.get("journey_stages", []))

            # Build sentiment
            sentiment_data = report_data.get("sentiment", {})
            sentiment = SentimentData(**sentiment_data)

            # Create the report
            report = PersonaReport(
                report_id=report_id,
                customer_id=request.customer_id,
                persona=persona,
                social_media_source=social_media if "social_media" in request.data_sources else None,
                first_party_source=first_party if "first_party" in request.data_sources else None,
                market_research_source=market if "market_research" in request.data_sources else None,
                journey_stages=journey_stages,
                sentiment=sentiment if request.include_sentiment else None,
                insights=report_data.get("insights", []),
                recommendations=report_data.get("recommendations", []) if request.include_recommendations else [],
            )

            # Cache the report
            self.report_cache[report_id] = report

            return PersonaReportResponse(
                success=True,
                report=report,
            )

        except Exception as e:
            print(f"Error generating report: {str(e)}")
            return PersonaReportResponse(
                success=False,
                error=str(e),
            )

    def get_report(self, report_id: str) -> Optional[PersonaReport]:
        """
        Retrieve a cached report by ID.

        Args:
            report_id: Report identifier

        Returns:
            PersonaReport or None if not found
        """
        return self.report_cache.get(report_id)

    def export_report_json(self, report: PersonaReport, output_path: str) -> bool:
        """
        Export report to JSON file.

        Args:
            report: PersonaReport to export
            output_path: Path where to save JSON

        Returns:
            True if successful, False otherwise
        """
        try:
            data = report.model_dump(mode="json", exclude_none=True)
            self.save_json(output_path, data)
            return True
        except Exception as e:
            print(f"Error exporting report: {str(e)}")
            return False
