"""
Python outreach draft validator enforcing Section 6.3 and 6.4 guardrails.
"""

from typing import Dict, Any, List, Tuple
import re


BANNED_PHRASES = [
    r"\bdiscount\b",
    r"\bprice cut\b",
    r"\bwaiver\b",
    r"\bspecial rate\b",
    r"\bguarantee\b",
    r"\bguaranteed\b",
    r"\bchurn\b",
    r"\bat risk\b",
    r"\bour model\b",
    r"\bscore\b",
    r"\blabel\b",
    r"\brank\b",
    r"\branked\b",
    r"\bdeadline\b",
    r"\bcommit\b",
    r"\bpromise\b",
]

# Competitor names or generic markers that shouldn't appear
COMPETITOR_PATTERNS = [
    r"\bpaytm\b",
    r"\bphonepe\b",
    r"\bbilldesk\b",
    r"\bccavenue\b",
    r"\bstripe\b",
    r"\bcompetitor\b",
]


def count_sentences(text: str) -> int:
    """Counts sentences using punctuation delimiters (. ! ?)."""
    # Split by sentence-ending punctuation followed by whitespace or end of string
    raw_sentences = re.split(r"[.!?]+(?:\s+|$)", text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return len(sentences)


def extract_numbers_from_text(text: str) -> List[float]:
    """Extracts all numeric tokens from text."""
    # Matches integers and decimals, excluding percentage signs or trailing dots
    matches = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    nums = []
    for m in matches:
        try:
            nums.append(float(m))
        except ValueError:
            pass
    return nums


def validate_draft(
    draft_text: str,
    merchant: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Validates outreach draft according to Section 6.3 and 6.4 guardrails.
    Returns (is_valid, list_of_errors).
    """
    errors: List[str] = []
    if not draft_text or not draft_text.strip():
        return False, ["Draft text is empty."]

    text = draft_text.strip()
    text_lower = text.lower()

    # 1. Sentence count (3 to 5 sentences)
    sentence_count = count_sentences(text)
    if sentence_count < 3 or sentence_count > 5:
        errors.append(f"Draft must have between 3 and 5 sentences (found {sentence_count}).")

    # 2. Addressed to correct business_name
    business_name = str(merchant.get("business_name") or "").strip()
    if business_name and business_name.lower() not in text_lower:
        errors.append(f"Draft must be explicitly addressed to the merchant's business name '{business_name}'.")

    # 3. Banned phrases check
    for pattern in BANNED_PHRASES:
        if re.search(pattern, text_lower):
            clean_word = pattern.replace(r"\b", "")
            errors.append(f"Prohibited term or commitment detected: '{clean_word}'.")

    # 4. Competitor mentions check
    for pattern in COMPETITOR_PATTERNS:
        if re.search(pattern, text_lower):
            errors.append(f"Forbidden competitor reference or note leak detected: '{pattern}'.")

    # 5. Check if note was quoted directly
    note = str(merchant.get("account_manager_note") or "").strip()
    if len(note) >= 20 and note.lower() in text_lower:
        errors.append("Draft must not quote the internal account manager note.")

    # 6. Numeric claims check: Every number must belong to this merchant's row or calculations
    allowed_numbers = set()
    # Collect all numbers from merchant dictionary
    for k, v in merchant.items():
        if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and (v != v or str(v) == "nan")):
            try:
                allowed_numbers.add(round(float(v), 1))
                allowed_numbers.add(round(float(v), 2))
                allowed_numbers.add(float(int(v)))
            except (ValueError, OverflowError):
                pass
        elif isinstance(v, str):
            for num in extract_numbers_from_text(v):
                allowed_numbers.add(round(num, 1))
                allowed_numbers.add(float(int(num)))

    # Also allow standard small integers used in polite phrasing (e.g. 15-minute call, 20-30 min)
    standard_call_lengths = {10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 1.0, 2.0}

    extracted_nums = extract_numbers_from_text(text)
    for num in extracted_nums:
        num_r1 = round(num, 1)
        num_int = float(int(num))
        if (
            num_r1 not in allowed_numbers
            and num_int not in allowed_numbers
            and num not in standard_call_lengths
        ):
            errors.append(
                f"Numeric claim {num} is not supported by merchant data or standard review call durations."
            )

    is_valid = len(errors) == 0
    return is_valid, errors
