"""
Urgency calculation, slot allocation, and portfolio ranking module.
"""

from typing import Dict, Any, List, Optional


URGENCY_RANKS = {
    "Urgent": 1,
    "Soon": 2,
    "Upcoming": 3,
    "none": 4,
}


def calculate_renewal_urgency(days: Optional[float], config: Dict[str, Any]) -> str:
    """
    Returns renewal urgency tier: Urgent, Soon, Upcoming, or none.
    """
    if days is None:
        return "none"
    urg_cfg = config.get("urgency_days", {})
    urgent_days = urg_cfg.get("urgent", 15)
    soon_days = urg_cfg.get("soon", 30)
    upcoming_days = urg_cfg.get("upcoming", 60)

    if days <= urgent_days:
        return "Urgent"
    elif days <= soon_days:
        return "Soon"
    elif days <= upcoming_days:
        return "Upcoming"
    return "none"


def rank_portfolio(
    merchants: List[Dict[str, Any]],
    config: Dict[str, Any],
    ranking_mode: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Ranks all merchants, allocates Contact now and Queued for flagged merchants,
    and returns fully ranked list with overall_rank, status, and urgency.
    """
    mode = ranking_mode or config.get("ranking_mode", "label_first")
    cap = config.get("cap", 15)

    # First add urgency to each merchant if not present
    for m in merchants:
        if "urgency" not in m:
            m["urgency"] = calculate_renewal_urgency(m.get("days_to_contract_renewal"), config)

    # Separate into groups: flagged, watch, other non-flagged
    flagged_merchants = [m for m in merchants if m.get("flagged") is True]
    watch_merchants = [m for m in merchants if not m.get("flagged") and m.get("non_flag_class") == "Watch"]
    other_non_flagged = [
        m for m in merchants if not m.get("flagged") and m.get("non_flag_class") != "Watch"
    ]

    # Helper sort keys
    def urgency_order(m):
        return URGENCY_RANKS.get(m.get("urgency", "none"), 4)

    def annual_val_sort_key(m):
        val = m.get("annual_value_rs")
        # Known value first (1), then val desc; unknown is (0, 0)
        if val is not None:
            return (1, val)
        return (0, 0.0)

    if mode == "label_first":
        # High before Medium; then annual value desc; then renewal urgency; then merchant_id asc
        def flagged_sort_key(m):
            label_rank = 1 if m.get("label") == "High" else 2
            val_known, val = annual_val_sort_key(m)
            urg = urgency_order(m)
            m_id = str(m.get("merchant_id", ""))
            # For reverse sorting on value, we construct a key:
            # (label_rank asc, val_known desc, val desc, urg asc, m_id asc)
            return (label_rank, -val_known, -val, urg, m_id)

        sorted_flagged = sorted(flagged_merchants, key=flagged_sort_key)
    else:  # value_first
        # Annual value desc regardless of label; then renewal urgency; then merchant_id asc
        def flagged_sort_key_val(m):
            val_known, val = annual_val_sort_key(m)
            urg = urgency_order(m)
            m_id = str(m.get("merchant_id", ""))
            return (-val_known, -val, urg, m_id)

        sorted_flagged = sorted(flagged_merchants, key=flagged_sort_key_val)

    # Assign Contact now and Queued
    contact_now_list = []
    queued_list = []
    for idx, m in enumerate(sorted_flagged):
        m_copy = dict(m)
        if idx < cap:
            m_copy["status"] = "Contact now"
            contact_now_list.append(m_copy)
        else:
            m_copy["status"] = "Queued"
            # Add time-critical note if Urgent or Soon
            if m_copy.get("urgency") in ["Urgent", "Soon"]:
                m_copy["queued_note"] = "time-critical: consider a low-touch contact"
            queued_list.append(m_copy)

    # Sort Watch merchants by annual value desc, urgency asc, merchant_id asc
    def watch_sort_key(m):
        val_known, val = annual_val_sort_key(m)
        urg = urgency_order(m)
        return (-val_known, -val, urg, str(m.get("merchant_id", "")))

    sorted_watch = sorted(watch_merchants, key=watch_sort_key)
    for m in sorted_watch:
        m["status"] = "Watch"

    # Sort other non-flagged: decline_pct desc (unknown last), annual_value desc, merchant_id asc
    def other_sort_key(m):
        dec = m.get("decline_pct")
        dec_known = 1 if dec is not None else 0
        dec_val = dec if dec is not None else -999999.0
        val_known, val = annual_val_sort_key(m)
        return (-dec_known, -dec_val, -val_known, -val, str(m.get("merchant_id", "")))

    sorted_others = sorted(other_non_flagged, key=other_sort_key)
    for m in sorted_others:
        m["status"] = m.get("non_flag_class", "No risk signal")

    # Combine into full ranked portfolio: Contact now, Queued, Watch, Others
    full_portfolio = contact_now_list + queued_list + sorted_watch + sorted_others
    for rank_idx, m in enumerate(full_portfolio, start=1):
        m["overall_rank"] = rank_idx

    return full_portfolio
