"""
Deterministic account-manager note tagger module.
"""

from typing import Dict, Any, Optional, Set
import re


ALLOWED_TAGS = [
    "COMPETITOR",
    "RATE_CARD",
    "SERVICE_OPEN",
    "PERF_COMPLAINT",
    "DISENGAGED",
    "SEASONAL_EXPLAINED",
    "RESOLVED",
    "POSITIVE",
    "NEUTRAL",
    "UNKNOWN",
    "BLANK",
]

TAG_PRECEDENCE = [
    "COMPETITOR",
    "RATE_CARD",
    "SERVICE_OPEN",
    "PERF_COMPLAINT",
    "DISENGAGED",
    "SEASONAL_EXPLAINED",
    "RESOLVED",
    "POSITIVE",
    "NEUTRAL",
]


def classify_note_deterministic(note: Optional[str], config: Dict[str, Any]) -> str:
    """
    Classifies an account manager note deterministically following Section 4.2 rules.
    """
    if note is None or str(note).strip() == "":
        return "BLANK"

    text = str(note).strip().lower()

    keywords_cfg = config.get("note_keywords", {})
    resolution_pattern = config.get("resolution_words", r"\b(fixed|resolved|sorted)\b|\bclosed\b")
    still_open_pattern = config.get(
        "still_open_markers",
        r"not (yet )?(closed|resolved|fixed)|\bstill\b|\bpending\b|\bunresolved\b|\bbut\b|\bhowever\b|no clear answer|\bagain\b",
    )

    # 2. Collect matched tags
    matched_tags: Set[str] = set()
    for tag, pattern in keywords_cfg.items():
        if re.search(pattern, text, re.IGNORECASE):
            matched_tags.add(tag)

    # 3. Resolved check
    has_resolution = bool(re.search(resolution_pattern, text, re.IGNORECASE))
    has_still_open = bool(re.search(still_open_pattern, text, re.IGNORECASE))

    if has_resolution and not has_still_open:
        # Drop SERVICE_OPEN and PERF_COMPLAINT, add RESOLVED
        matched_tags.discard("SERVICE_OPEN")
        matched_tags.discard("PERF_COMPLAINT")
        matched_tags.add("RESOLVED")

    # 4. Final tag by precedence
    for candidate in TAG_PRECEDENCE:
        if candidate in matched_tags:
            return candidate

    # 5. No match
    return "UNKNOWN"
