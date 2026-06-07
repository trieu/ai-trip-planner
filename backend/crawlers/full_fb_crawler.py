"""
LEO CDP Social Trend Listening Pipeline

Requirements:
    pip install scrapling[fetchers]
    pip install google-genai
    pip install pydantic

Environment:
    GEMINI_API_KEY=xxxx

Flow:
    DynamicFetcher
        -> Raw Text
        -> Gemini Structured Extraction
        -> FacebookPost Schema
        -> LEO CDP Event
        -> Knowledge Hub
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from scrapling.fetchers import DynamicFetcher


# =====================================================
# CONFIG
# =====================================================

MODEL_NAME = "gemini-3.1-flash-lite"

SOCIAL_SOURCE_URL = "https://www.facebook.com/dataism.one"

# Only posts mentioning at least one of these important keywords are kept.
# Use product names, company names or brands here - NOT a full crawl.
# Leave empty to disable filtering (keep every extracted post).
IMPORTANT_KEYWORDS: List[str] = [
    "dataism",
    "leo cdp",
    "usee",
]

# Max number of characters from the post content used to build the
# idempotent (dedupe) key. Keeps the key stable for long posts.
IDEMPOTENT_CONTENT_MAX_CHARS = 1000

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")

if not GOOGLE_GEMINI_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is not set.")

client = genai.Client(
    api_key=GOOGLE_GEMINI_API_KEY
)


# =====================================================
# SCHEMA
# =====================================================

class FacebookPost(BaseModel):
    post_id: Optional[str] = None

    page_name: Optional[str] = None

    author: Optional[str] = None

    created_at: Optional[str] = None

    # post, video, photo, reel, share, ...
    post_type: Optional[str] = None

    content: str

    hashtags: List[str] = Field(default_factory=list)

    keywords: List[str] = Field(default_factory=list)

    mentioned_people: List[str] = Field(default_factory=list)

    mentioned_brands: List[str] = Field(default_factory=list)

    sentiment: Optional[str] = None

    topic: Optional[str] = None


class FacebookPageData(BaseModel):
    page_name: Optional[str] = None

    posts: List[FacebookPost]


# =====================================================
# LEO CDP EVENT MODEL
# =====================================================

class LeoSocialEvent(BaseModel):

    event_id: str

    source: str

    source_url: str

    collected_at: str

    page_name: Optional[str]

    topic: Optional[str]

    sentiment: Optional[str]

    content: str

    keywords: List[str]

    hashtags: List[str]

    mentioned_people: List[str]

    mentioned_brands: List[str]

    raw_data: dict


# =====================================================
# FETCH
# =====================================================

def fetch_social_page(url: str) -> str:

    page = DynamicFetcher.fetch(
        url,
        timeout=60000,
        network_idle=True,
    )

    print(f"Status: {page.status}")

    text = page.get_all_text()

    print(f"Fetched text length: {len(text)}")

    return text


# =====================================================
# GEMINI EXTRACTION
# =====================================================

def extract_posts(raw_text: str) -> FacebookPageData:

    if IMPORTANT_KEYWORDS:
        keyword_rule = (
            "- ONLY extract posts that mention at least one of these "
            "important keywords (product/company/brand): "
            + ", ".join(IMPORTANT_KEYWORDS)
            + "\n- Skip every post that does not mention any of them"
        )
    else:
        keyword_rule = "- Extract visible posts only"

    prompt = f"""
You are a social listening extraction engine.

Extract meaningful Facebook posts from the text.

Rules:

- Ignore menus
- Ignore navigation
- Ignore ads
- Ignore login messages
{keyword_rule}
- Detect topic
- Detect sentiment
- Detect post_type (post, video, photo, reel, share)
- Extract hashtags
- Extract keywords
- Extract people
- Extract brands

Content:

{raw_text[:100000]}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": FacebookPageData,
        },
    )

    return response.parsed


# =====================================================
# FILTER
# =====================================================

def post_matches_keywords(post: FacebookPost) -> bool:
    """True if the post mentions any important keyword.

    Matches against content, extracted keywords and mentioned brands
    (case-insensitive). No keywords configured => keep everything.
    """
    if not IMPORTANT_KEYWORDS:
        return True

    haystack = " ".join([
        post.content or "",
        " ".join(post.keywords),
        " ".join(post.mentioned_brands),
    ]).lower()

    return any(kw.lower() in haystack for kw in IMPORTANT_KEYWORDS)


def filter_posts_by_keywords(
    page_data: FacebookPageData,
) -> FacebookPageData:

    kept = [p for p in page_data.posts if post_matches_keywords(p)]

    print(
        f"Keyword filter: kept {len(kept)}/{len(page_data.posts)} posts "
        f"(keywords={IMPORTANT_KEYWORDS or 'ALL'})"
    )

    return FacebookPageData(page_name=page_data.page_name, posts=kept)


# =====================================================
# NORMALIZATION
# =====================================================

def platform_host(source_url: str) -> str:
    """Bare host of the source platform, e.g. facebook.com, vnexpress.net."""
    host = (urlparse(source_url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def build_idempotent_key(
    post: FacebookPost,
    host: str,
) -> str:
    """Deterministic dedupe key for a post.

    Built from: content[:1000] + author + post date + post type + host.
    Re-crawling the same post yields the same key, so the CDP can dedupe.
    """
    parts = [
        (post.content or "")[:IDEMPOTENT_CONTENT_MAX_CHARS].strip(),
        (post.author or "").strip(),
        (post.created_at or "").strip(),
        (post.post_type or "").strip(),
        host,
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_leo_events(
    source_url: str,
    page_data: FacebookPageData,
) -> List[LeoSocialEvent]:

    host = platform_host(source_url)

    events = []

    for post in page_data.posts:

        event = LeoSocialEvent(
            event_id=build_idempotent_key(post, host),
            source="facebook",
            source_url=source_url,
            collected_at=datetime.now(timezone.utc).isoformat(),
            page_name=post.page_name or page_data.page_name,
            topic=post.topic,
            sentiment=post.sentiment,
            content=post.content,
            keywords=post.keywords,
            hashtags=post.hashtags,
            mentioned_people=post.mentioned_people,
            mentioned_brands=post.mentioned_brands,
            raw_data=post.model_dump(),
        )

        events.append(event)

    return events


# =====================================================
# LEO CDP INGEST
# =====================================================

def ingest_to_leo_cdp(events: List[LeoSocialEvent]):

    for event in events:

        payload = event.model_dump()

        print("=" * 80)
        print("INGEST EVENT")
        print(json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ))

        #
        # Example:
        #
        # requests.post(
        #     f"{LEO_CDP_URL}/api/social-events",
        #     headers={
        #         "Authorization": f"Bearer {TOKEN}"
        #     },
        #     json=payload
        # )
        #


# =====================================================
# TREND AGGREGATION
# =====================================================

def build_trend_summary(events: List[LeoSocialEvent]):

    trend_counter = {}

    for event in events:

        for keyword in event.keywords:

            trend_counter[keyword] = (
                trend_counter.get(keyword, 0) + 1
            )

    top_trends = sorted(
        trend_counter.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:20]

    print("\nTOP TRENDS")
    print("=" * 80)

    for keyword, score in top_trends:
        print(f"{keyword}: {score}")


# =====================================================
# MAIN
# =====================================================

def main():

    raw_text = fetch_social_page(
        SOCIAL_SOURCE_URL
    )

    page_data = extract_posts(
        raw_text
    )

    page_data = filter_posts_by_keywords(
        page_data
    )

    print(
        page_data.model_dump_json(
            indent=2,
            ensure_ascii=False,
        )
    )

    events = build_leo_events(
        SOCIAL_SOURCE_URL,
        page_data,
    )

    ingest_to_leo_cdp(events)

    build_trend_summary(events)


if __name__ == "__main__":
    main()
