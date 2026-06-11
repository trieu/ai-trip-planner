#!/usr/bin/env python3

"""
Travel Booking + AI Travel Research CDP Data Generator

Features
--------
- ArangoDB compatible _key generation
- Realistic customer segments
- Travel research behaviors
- AI Trip Planner activities
- Loyalty program simulation
- Travel booking transactions
- Journey scoring
- CLV simulation
- Campaign attribution
- Customer 360 profile generation

Usage
-----

python generate_travel_cdp.py \
    --profiles 200 \
    --output travel_ai_cdp.json

python generate_travel_cdp.py \
    --profiles 1000 \
    --output enterprise_travel_cdp.json

"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import secrets
import string

from copy import deepcopy
from enum import Enum
from pathlib import Path
from datetime import datetime, timedelta


# ============================================================
# CONFIG
# ============================================================

KEY_LENGTH = 22

KEY_CHARS = (
    string.ascii_letters +
    string.digits
)

FIRST_NAMES = [
    "An",
    "Minh",
    "Linh",
    "Trang",
    "Nam",
    "Vy",
    "Khanh",
    "Long",
    "Phuong",
    "Huy",
    "Quynh",
    "Thanh",
    "Bao",
    "Ngoc",
    "Tuan"
]

CITIES = [
    "Ha Noi",
    "Ho Chi Minh City",
    "Da Nang",
    "Can Tho",
    "Hai Phong"
]

DESTINATIONS = [
    "Tokyo",
    "Osaka",
    "Kyoto",
    "Seoul",
    "Bangkok",
    "Singapore",
    "Bali",
    "Phu Quoc",
    "Paris",
    "London",
    "Dubai",
    "Hong Kong"
]

TRAVEL_QUERIES = [
    "best hotels in tokyo",
    "tokyo itinerary 5 days",
    "cheap flights to seoul",
    "family vacation bali",
    "business hotel singapore",
    "visa requirements japan",
    "travel insurance asia",
    "best beach resort phu quoc",
    "luxury hotel bangkok",
    "best time to visit paris",
    "family hotel london",
    "airport transfer tokyo",
]

EVENT_TYPES = [
    "hotel-search",
    "flight-search",
    "destination-research",
    "ai-trip-planner",
    "price-alert-signup",
    "booking-started",
    "booking-completed",
    "loyalty-scan",
    "hotel-checkin",
    "hotel-review"
]

TOUCHPOINTS = [
    {
        "name": "AI Trip Planner",
        "hostname": "travel.demo.ai",
        "url": "https://travel.demo.ai/planner"
    },
    {
        "name": "Hotel Search",
        "hostname": "travel.demo.ai",
        "url": "https://travel.demo.ai/hotels"
    },
    {
        "name": "Flight Search",
        "hostname": "travel.demo.ai",
        "url": "https://travel.demo.ai/flights"
    },
    {
        "name": "Destination Guide",
        "hostname": "travel.demo.ai",
        "url": "https://travel.demo.ai/guides"
    }
]

TEMPLATE = {
    "activationTimeline": {},
    "age": 0,
    "ageGroup": 0,
    "applicationIDs": [],
    "authorizedEditors": [],
    "authorizedViewers": [],
    "behavioralEvents": [],
    "businessContacts": {},
    "businessData": {},
    "businessIndustries": [],
    "churnScore": 0,
    "contactAddresses": [],
    "contentKeywords": [],
    "contextSessionKeys": {},
    "currentZipCode": "",
    "dataContext": 1,
    "dataLabels": [],
    "dataLabelsAsStr": "",
    "dataQualityScore": 80,
    "dataVerification": False,
    "eventStatistics": {},
    "extAttributes": {},
    "extMetrics": {},
    "financeCreditEvents": [],
    "financeRecords": [],
    "fintechSystemIDs": [],
    "fromTouchpointHubIds": ["travel_hub_01"],
    "funnelStage": "lead",
    "googleUtmData": [],
    "governmentIssuedIDs": [],
    "housingType": "",
    "inAccounts": [],
    "inAccountsAsStr": "",
    "inCampaigns": [],
    "inCampaignsAsStr": "",
    "inJourneyMaps": [],
    "inJourneyMapsAsStr": "",
    "inSegments": [],
    "inSegmentsAsStr": "",
    "incomeHistory": {},
    "jobTitles": [],
    "jobType": -1,
    "lastName": "",
    "learningCourses": [],
    "learningHistory": [],
    "loyaltyIDs": [],
    "mediaChannels": [],
    "nextBestActions": [],
    "paymentEvents": [],
    "personalInterests": [],
    "personalProblems": [],
    "personalityTypes": [],
    "productKeywords": [],
    "purchasedBrands": [],
    "purchasedItemIds": [],
    "purchasedItems": [],
    "receiveAds": 1,
    "receiveEmail": 1,
    "receiveSMS": 1,
    "receiveWebPush": 0,
    "rfmScore": 0,
    "saleAgencies": [],
    "saleAgents": [],
    "schemaType": "general",
    "secondaryEmails": [],
    "secondaryPhones": [],
    "shoppingItemIds": [],
    "shoppingItems": [],
    "similarProfiles": [],
    "socialMediaProfiles": {},
    "softSkills": [],
    "solutionsForCustomer": [],
    "status": 1,
    "studyCertificates": [],
    "subscribedChannels": {},
    "type": 2
}


# ============================================================
# SEGMENTS
# ============================================================

class ProfileSegment(str, Enum):
    VISITOR = "visitor"
    RESEARCHER = "researcher"
    TRAVELER = "traveler"
    LOYALTY = "loyalty"
    VIP = "vip"


# ============================================================
# HELPERS
# ============================================================

def generate_key(length: int = KEY_LENGTH) -> str:
    return "".join(
        secrets.choice(KEY_CHARS)
        for _ in range(length)
    )


def random_date() -> str:
    dt = (
        datetime(2025, 1, 1) +
        timedelta(days=random.randint(0, 365))
    )

    return dt.isoformat() + "Z"


def generate_fingerprint(email: str) -> str:
    return hashlib.sha256(
        email.encode()
    ).hexdigest()


def generate_segment_distribution(total: int):

    segments = []

    ratios = [
        (ProfileSegment.VISITOR, 0.20),
        (ProfileSegment.RESEARCHER, 0.30),
        (ProfileSegment.TRAVELER, 0.30),
        (ProfileSegment.LOYALTY, 0.15),
        (ProfileSegment.VIP, 0.05)
    ]

    for segment, ratio in ratios:
        segments.extend(
            [segment] * int(total * ratio)
        )

    while len(segments) < total:
        segments.append(
            ProfileSegment.RESEARCHER
        )

    random.shuffle(segments)

    return segments


# ============================================================
# BUSINESS LOGIC
# ============================================================

def generate_loyalty(segment):

    if segment == ProfileSegment.VIP:
        return "Platinum", random.randint(
            150_000,
            500_000
        )

    if segment == ProfileSegment.LOYALTY:
        return "Gold", random.randint(
            50_000,
            150_000
        )

    if segment == ProfileSegment.TRAVELER:
        return "Silver", random.randint(
            10_000,
            50_000
        )

    return "", 0


def generate_clv(segment):

    ranges = {
        ProfileSegment.VISITOR: (0, 0),
        ProfileSegment.RESEARCHER: (0, 0),
        ProfileSegment.TRAVELER: (
            5_000_000,
            50_000_000
        ),
        ProfileSegment.LOYALTY: (
            50_000_000,
            200_000_000
        ),
        ProfileSegment.VIP: (
            200_000_000,
            1_000_000_000
        ),
    }

    low, high = ranges[segment]

    return random.randint(
        low,
        high
    )


def generate_booking():

    destination = random.choice(
        DESTINATIONS
    )

    value = random.randint(
        3_000_000,
        50_000_000
    )

    return {
        "bookingId":
            f"BK-{random.randint(100000,999999)}",

        "destination":
            destination,

        "bookingType":
            random.choice([
                "Flight",
                "Hotel",
                "Package"
            ]),

        "transactionValue":
            value,

        "currency":
            "VND"
    }


def generate_touchpoint():
    return random.choice(
        TOUCHPOINTS
    )


# ============================================================
# PROFILE GENERATOR
# ============================================================

def generate_profile(
    index: int,
    segment: ProfileSegment
):

    p = deepcopy(TEMPLATE)

    email = (
        f"user{index}@traveldemo.ai"
    )

    crm = str(
        500000000000000000 + index
    )

    visitor = (
        f"visitor{index:05d}"
    )

    fp = generate_fingerprint(
        email
    )

    created = random_date()

    loyalty_tier, loyalty_points = (
        generate_loyalty(segment)
    )

    booking = None

    if segment in [
        ProfileSegment.TRAVELER,
        ProfileSegment.LOYALTY,
        ProfileSegment.VIP
    ]:
        booking = generate_booking()

    clv = generate_clv(segment)

    touchpoint = generate_touchpoint()

    p.update({

        "_key":
            generate_key(),

        "createdAt":
            created,

        "updatedAt":
            created,

        "updatedByCrmAt":
            created,

        "crmRefId":
            crm,

        "fingerprintId":
            fp,

        "firstName":
            random.choice(
                FIRST_NAMES
            ),

        "livingLocation":
            random.choice(
                CITIES
            ),

        "journeyScore":
            random.randint(
                10,
                100
            ),

        "rfmScore":
            random.randint(
                1,
                100
            ),

        "churnScore":
            random.randint(
                0,
                80
            ),

        "dataQualityScore":
            random.randint(
                70,
                99
            ),

        "primaryEmail":
            email,

        "visitorId":
            visitor,

        "identities": [
            f"visitor:{visitor}",
            f"fgp:{fp}",
            f"email:{email}",
            f"crm:{crm}"
        ],

        "identitiesAsStr":
            (
                f"visitor:{visitor};"
                f"email:{email}"
            ),

        "behavioralEvents":
            random.sample(
                EVENT_TYPES,
                k=3
            ),

        "contentKeywords":
            random.sample(
                TRAVEL_QUERIES,
                k=random.randint(
                    2,
                    5
                )
            ),

        "personalInterests": [
            "Travel",
            "AI Travel Planning",
            random.choice(
                DESTINATIONS
            )
        ],

        "personalProblems": [
            "finding affordable flights",
            "hotel comparison"
        ],

        "googleUtmData": [{
            "utm_source":
                random.choice([
                    "google",
                    "facebook",
                    "youtube"
                ]),
            "utm_medium":
                random.choice([
                    "cpc",
                    "search",
                    "video"
                ]),
            "utm_campaign":
                random.choice([
                    "japan_2026",
                    "summer_travel",
                    "family_trip"
                ])
        }],

        "extAttributes": {
            "segment":
                segment.value,

            "loyaltyTier":
                loyalty_tier,

            "loyaltyPoints":
                loyalty_points,

            "preferredDestination":
                random.choice(
                    DESTINATIONS
                )
        },

        "nextBestActions": [
            "Recommend destination package",
            "Offer travel insurance",
            "Offer airport transfer"
        ],

        "mediaChannels": [
            "website",
            "mobile-app"
        ],

        "totalCLV":
            clv,

        "totalTransactionValue":
            booking["transactionValue"]
            if booking else 0,

        "lastPurchaseEvent":
            booking,

        "paymentEvents":
            [booking]
            if booking else [],

        "lastTrackingEvent": {
            "metricName":
                random.choice(
                    EVENT_TYPES
                ),

            "metricValue":
                1,

            "eventData": {
                "query":
                    random.choice(
                        TRAVEL_QUERIES
                    ),

                "usedAIPlanner":
                    True,

                "destination":
                    random.choice(
                        DESTINATIONS
                    )
            }
        },

        "lastTouchpoint":
            touchpoint
    })

    return p


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--profiles",
        type=int,
        default=200
    )

    parser.add_argument(
        "--output",
        default=
        "travel_ai_cdp.json"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42
    )

    args = parser.parse_args()

    random.seed(args.seed)

    segments = (
        generate_segment_distribution(
            args.profiles
        )
    )

    profiles = [
        generate_profile(
            i,
            segment
        )
        for i, segment
        in enumerate(segments)
    ]

    output_file = Path(
        args.output
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            profiles,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Generated "
        f"{len(profiles)} profiles"
    )

    print(
        f"Saved to "
        f"{output_file}"
    )


if __name__ == "__main__":
    main()