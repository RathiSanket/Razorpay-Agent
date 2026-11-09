"""
Value scenario calculations, driver aggregation, and static process recommendations.
"""

from typing import Dict, Any, List, Optional


STATIC_PROCESS_FIXES = {
    "PB-3": (
        "Add a structured 'competitor or pricing request' field in the CRM and start a "
        "commercial review 90 days before renewal. Commercial risk is visible through notes, "
        "so it can be missed when notes are blank."
    ),
    "PB-1": (
        "Alert Payments Ops when a merchant's success rate drops 5 or more points."
    ),
    "PB-2": (
        "Auto-escalate tickets unresolved beyond an agreed number of days."
    ),
    "PB-4": (
        "Usage-health check-ins and a confirmed contact person."
    ),
}

PLAYBOOK_TITLES = {
    "PB-1": "Performance (PB-1)",
    "PB-2": "Service (PB-2)",
    "PB-3": "Commercial (PB-3)",
    "PB-4": "Disengagement (PB-4)",
    "PB-5": "Growth (PB-5)",
    "PB-6": "Monitor / No Action (PB-6)",
}


def calculate_value_scenario(
    portfolio: List[Dict[str, Any]],
    config: Dict[str, Any],
    churn_likelihood: Optional[float] = None,
    save_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes value at stake, costs, net value, and break-even save rate for Contact now merchants.
    """
    scenario_cfg = config.get("scenario", {})
    p_churn = churn_likelihood if churn_likelihood is not None else scenario_cfg.get("churn_likelihood", 0.75)
    s_rate = save_rate if save_rate is not None else scenario_cfg.get("save_rate", 0.25)
    cost_per_outreach = config.get("cost_per_outreach_rs", 1500.0)

    contacted = [m for m in portfolio if m.get("status") == "Contact now"]
    contacted_count = len(contacted)

    # value_at_stake = sum(annual_value_rs for Contact now merchants)
    value_at_stake = sum(
        m.get("annual_value_rs") for m in contacted if m.get("annual_value_rs") is not None
    )
    cost = contacted_count * cost_per_outreach
    net_value = (value_at_stake * p_churn * s_rate) - cost

    break_even_save: Optional[float] = None
    denominator = value_at_stake * p_churn
    if denominator > 0:
        break_even_save = (cost / denominator) * 100.0  # as percentage

    # Per-merchant cost as % of annual value
    merchant_costs = []
    for m in contacted:
        ann_val = m.get("annual_value_rs")
        cost_pct = (cost_per_outreach / ann_val * 100.0) if ann_val and ann_val > 0 else None
        merchant_costs.append({
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "annual_value_rs": ann_val,
            "cost_rs": cost_per_outreach,
            "cost_pct_of_value": cost_pct,
        })

    return {
        "contacted_count": contacted_count,
        "cost_per_outreach_rs": cost_per_outreach,
        "churn_likelihood": p_churn,
        "save_rate": s_rate,
        "value_at_stake_rs": value_at_stake,
        "total_cost_rs": cost,
        "net_value_rs": net_value,
        "break_even_save_pct": break_even_save,
        "merchant_costs": merchant_costs,
    }


def aggregate_drivers(portfolio: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Groups flagged merchants by primary playbook and provides driver breakdown and process fixes.
    """
    flagged = [m for m in portfolio if m.get("flagged") is True]

    driver_stats: Dict[str, Dict[str, Any]] = {}
    for pb_id in ["PB-1", "PB-2", "PB-3", "PB-4"]:
        driver_stats[pb_id] = {
            "playbook_id": pb_id,
            "name": PLAYBOOK_TITLES.get(pb_id, pb_id),
            "flagged_count": 0,
            "annual_value_at_stake": 0.0,
            "contact_now_count": 0,
        }

    for m in flagged:
        pb = m.get("primary_playbook")
        if pb in driver_stats:
            driver_stats[pb]["flagged_count"] += 1
            ann_val = m.get("annual_value_rs") or 0.0
            driver_stats[pb]["annual_value_at_stake"] += ann_val
            if m.get("status") == "Contact now":
                driver_stats[pb]["contact_now_count"] += 1

    driver_list = list(driver_stats.values())
    # Identify largest driver by annual value at stake
    largest_driver = max(driver_list, key=lambda d: d["annual_value_at_stake"]) if driver_list else None
    suggested_fix = (
        STATIC_PROCESS_FIXES.get(largest_driver["playbook_id"], "")
        if largest_driver and largest_driver["flagged_count"] > 0
        else ""
    )

    return {
        "drivers": driver_list,
        "largest_driver": largest_driver,
        "suggested_fix": suggested_fix,
    }
