
import re
import unicodedata

# ============================================================
# Canonical aliases
# ============================================================
CITY_ALIASES = {
    "saigon": "ho chi minh city",
    "hcm": "ho chi minh city",
    "hcmc": "ho chi minh city",
    "tphcm": "ho chi minh city",
    "danang": "da nang",
    "hn": "hanoi",
    "ha noi": "hanoi"
}

VIETNAM_KEYWORDS = {"viet", "vietnam", "vn",
                    "tphcm", "hcm", "saigon", "hanoi", "danang"}

# ============================================================
# Normalization helpers
# ============================================================


def normalize_text(text: str) -> str:
    """
    Normalize text for geocoding.

    Steps:
    - Lowercase
    - Vietnamese-specific letter normalization (đ → d)
    - Unicode NFKD normalization
    - Remove diacritics
    - Remove punctuation
    - Collapse whitespace
    """
    text = text.strip().lower()

    # 🔴 CRITICAL: Vietnamese-specific normalization
    text = text.replace("đ", "d").replace("Đ", "d")

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def canonicalize_city_name(raw: str) -> str:
    """
    Convert a city name to its canonical form using alias mapping.

    Args:
        raw: Original user-provided city name.

    Returns:
        Canonical city name suitable for geocoding.
    """
    normalized = normalize_text(raw)
    return CITY_ALIASES.get(normalized, normalized)


def looks_vietnamese(text: str) -> bool:
    """
    Heuristically detect whether a location is likely in Vietnam.

    Args:
        text: User-provided location string.

    Returns:
        True if Vietnamese indicators are detected, else False.
    """
    t = normalize_text(text)
    return any(k in t for k in VIETNAM_KEYWORDS)

# ================================
# to merge duplicate data 
# ================================
def merge_unique_csv(prof: dict, *keys: str, sep: str = ', ') -> str:
    """
    Merge multiple interest fields from a profile dict into a unique, ordered CSV string.

    - Supports values as: None, str, list/tuple/set, mixed types
    - Deduplicates while preserving order (first occurrence wins)
    - Casts all values to string
    """

    def to_list(v):
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, (list, tuple, set)):
            return list(v)
        return [str(v)]

    seen = set()
    merged = []

    for key in keys:
        values = to_list(prof.get(key))
        for item in values:
            s = str(item)
            if s not in seen:
                seen.add(s)
                merged.append(s)

    return sep.join(merged)