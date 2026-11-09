"""
Deterministic risk scoring, cause grading, labeling, and playbook selection.
"""

from typing import Dict, Any, List, Optional, Tuple


PLAYBOOK_NAMES = {
    "PB-1": "Performance Review",
    "PB-2": "Service Escalation",
    "PB-3": "Commercial & Pricing Review",
    "PB-4": "Usage & Re-engagement",
    "PB-5": "Growth Upsell",
    "PB-6": "Monitor / No Action",
}

CAUSE_TO_PLAYBOOK = {
    "Commercial": "PB-3",
    "Performance": "PB-1",
    "Service": "PB-2",
    "Disengagement": "PB-4",
}

# Tie-breaker order for primary playbook when levels tie:
TIE_ORDER = ["Commercial", "Performance", "Service", "Disengagement"]


def grade_causes(
    row: Dict[str, Any],
    features: Dict[str, Any],
    note_tag: str,
    config: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    Grades causes 0 to 3 for Performance, Service, Disengagement, and Commercial.
    Retains the exact rule and triggering values that produced the level.
    """
    sr_drop = features.get("sr_drop_pts")
    perf_cfg = config.get("performance", {})
    sr_l2 = perf_cfg.get("sr_drop_level2", 5.0)
    sr_l3 = perf_cfg.get("sr_drop_level3", 8.0)

    # 1. Performance (PB-1)
    perf_level = 0
    perf_evidence = ""
    if sr_drop is not None and sr_drop >= sr_l3:
        perf_level = 3
        sr1 = row.get("success_rate_m1_m3_pct")
        sr2 = row.get("success_rate_m4_m6_pct")
        perf_evidence = f"Success rate dropped {sr_drop:.1f} pts ({sr1:.1f}% to {sr2:.1f}%) [>= {sr_l3} pts]"
    elif sr_drop is not None and sr_drop >= sr_l2:
        perf_level = 2
        sr1 = row.get("success_rate_m1_m3_pct")
        sr2 = row.get("success_rate_m4_m6_pct")
        perf_evidence = f"Success rate dropped {sr_drop:.1f} pts ({sr1:.1f}% to {sr2:.1f}%) [>= {sr_l2} pts]"
    elif note_tag == "PERF_COMPLAINT":
        perf_level = 1
        note_snippet = (row.get("account_manager_note") or "")[:80]
        perf_evidence = f"Account note reported payment/UPI complaints: \"{note_snippet}\""

    # 2. Service (PB-2)
    serv_cfg = config.get("service", {})
    u_l1 = serv_cfg.get("unresolved_level1", 2)
    u_l2 = serv_cfg.get("unresolved_level2", 3)
    u_l3 = serv_cfg.get("unresolved_level3", 5)
    csat_max = serv_cfg.get("low_csat_max", 2.0)
    csat_min_tickets = serv_cfg.get("low_csat_min_tickets", 3)

    unresolved = row.get("unresolved_tickets")
    csat = row.get("last_csat_1_to_5")
    tickets_90d = row.get("support_tickets_last_90d")

    serv_level = 0
    serv_evidence = ""
    if unresolved is not None and unresolved >= u_l3:
        serv_level = 3
        serv_evidence = f"{int(unresolved)} unresolved support tickets [>= {u_l3}]"
    elif unresolved is not None and unresolved >= u_l2:
        serv_level = 2
        serv_evidence = f"{int(unresolved)} unresolved support tickets [3-4]"
    else:
        # Check level 1 conditions
        conds = []
        if unresolved is not None and unresolved == u_l1:
            conds.append(f"{int(unresolved)} unresolved tickets")
        if (
            csat is not None
            and csat <= csat_max
            and tickets_90d is not None
            and tickets_90d >= csat_min_tickets
        ):
            conds.append(f"low CSAT ({csat:.1f} <= {csat_max}) with {int(tickets_90d)} tickets")
        if note_tag == "SERVICE_OPEN":
            note_snippet = (row.get("account_manager_note") or "")[:80]
            conds.append(f"open service complaint in note: \"{note_snippet}\"")
        if conds:
            serv_level = 1
            serv_evidence = "; ".join(conds)

    # 3. Disengagement (PB-4)
    dis_cfg = config.get("disengagement", {})
    max_logins = dis_cfg.get("max_logins", 3)
    severe_logins = dis_cfg.get("severe_logins", 1)
    max_products = dis_cfg.get("max_products", 2)
    min_dec = dis_cfg.get("min_decline_pct", 20.0)

    logins = row.get("logins_last_30d")
    products = row.get("products_used")
    decline = features.get("decline_pct")

    dis_level = 0
    dis_evidence = ""
    if (
        logins is not None
        and logins <= severe_logins
        and products is not None
        and products <= max_products
        and decline is not None
        and decline >= min_dec
    ):
        dis_level = 3
        dis_evidence = f"Logins {int(logins)} <= {severe_logins}, products {int(products)} <= {max_products}, decline {decline:.1f}% >= {min_dec}%"
    elif (
        logins is not None
        and logins <= max_logins
        and products is not None
        and products <= max_products
        and decline is not None
        and decline >= min_dec
    ):
        dis_level = 2
        dis_evidence = f"Logins {int(logins)} <= {max_logins}, products {int(products)} <= {max_products}, decline {decline:.1f}% >= {min_dec}%"
    elif note_tag == "DISENGAGED":
        dis_level = 1
        note_snippet = (row.get("account_manager_note") or "")[:80]
        dis_evidence = f"Account note indicated disengagement: \"{note_snippet}\""

    # 4. Commercial (PB-3)
    comm_cfg = config.get("commercial", {})
    renewal_window = comm_cfg.get("renewal_window_days", 60)
    renewal_days = row.get("days_to_contract_renewal")

    comm_level = 0
    comm_evidence = ""
    if (
        note_tag == "COMPETITOR"
        and renewal_days is not None
        and renewal_days <= renewal_window
    ):
        comm_level = 3
        note_snippet = (row.get("account_manager_note") or "")[:80]
        comm_evidence = f"Competitor quote/interest with contract renewal in {int(renewal_days)} days (<= {renewal_window}d): \"{note_snippet}\""
    elif (
        note_tag == "RATE_CARD"
        and renewal_days is not None
        and renewal_days <= renewal_window
    ):
        comm_level = 1
        note_snippet = (row.get("account_manager_note") or "")[:80]
        comm_evidence = f"Rate card/pricing review inquiry with renewal in {int(renewal_days)} days (<= {renewal_window}d): \"{note_snippet}\""

    return {
        "Commercial": {"level": comm_level, "evidence": comm_evidence, "playbook": "PB-3"},
        "Performance": {"level": perf_level, "evidence": perf_evidence, "playbook": "PB-1"},
        "Service": {"level": serv_level, "evidence": serv_evidence, "playbook": "PB-2"},
        "Disengagement": {"level": dis_level, "evidence": dis_evidence, "playbook": "PB-4"},
    }


def assess_merchant_risk(
    row: Dict[str, Any],
    features: Dict[str, Any],
    note_tag: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Evaluates flagged status, risk label, Watch tier, non-flag class, playbooks, and reason.
    """
    causes = grade_causes(row, features, note_tag, config)
    decline_pct = features.get("decline_pct")
    growth_pct = features.get("growth_pct")
    proj_loss = features.get("proj_loss_90d")
    step_rebound = features.get("step_rebound")
    tpv_m6 = row.get("tpv_m6_inr_lakh")
    industry = row.get("industry")

    decline_gate = config.get("decline_gate_pct", 10.0)
    seasonal_industries = config.get("seasonal_industries", [])
    watch_min_lvl = config.get("watch_min_level", 2)
    low_vol_limit = config.get("low_volume_lakh", 5.0)
    growth_min = config.get("growth_min_pct", 15.0)

    # Active causes
    active_causes = {name: c for name, c in causes.items() if c["level"] >= 1}
    signal_count = len(active_causes)
    top_level = max(c["level"] for c in causes.values())

    max_ops_level = max(
        causes["Performance"]["level"],
        causes["Service"]["level"],
        causes["Disengagement"]["level"],
    )

    # Flag condition:
    # (decline_pct >= 10 AND max(Performance, Service, Disengagement) >= 1) OR Commercial >= 1
    has_ops_decline = (
        decline_pct is not None
        and decline_pct >= decline_gate
        and max_ops_level >= 1
    )
    has_commercial = causes["Commercial"]["level"] >= 1
    flagged = bool(has_ops_decline or has_commercial)

    # Label calculation
    label = "Low"
    non_flag_class = None

    if flagged:
        # High condition: number_of_active_causes >= 2 OR (proj_loss_90d is known AND proj_loss_90d <= -50)
        is_severe_proj = proj_loss is not None and proj_loss <= -config.get("label", {}).get("projected_loss_high_pct", 50.0)
        if signal_count >= config.get("label", {}).get("min_causes_for_high", 2) or is_severe_proj:
            label = "High"
        else:
            label = "Medium"
    else:
        label = "Low"
        # Non-flag class determination:
        # 1. Watch: max(Performance, Service, Disengagement) >= 2
        if max_ops_level >= watch_min_lvl:
            non_flag_class = "Watch"
        # 2. Growth (PB-5): growth_pct >= 15
        elif growth_pct is not None and growth_pct >= growth_min:
            non_flag_class = "Growth"
        # 3. Seasonal (PB-6): industry in seasonal_industries, step_rebound is True, decline_pct >= 10
        elif (
            industry in seasonal_industries
            and step_rebound is True
            and decline_pct is not None
            and decline_pct >= decline_gate
        ):
            non_flag_class = "Seasonal"
        # 4. Low-volume stable (PB-6): tpv_m6 < 5 and decline_pct < 10
        elif (
            tpv_m6 is not None
            and tpv_m6 < low_vol_limit
            and decline_pct is not None
            and decline_pct < decline_gate
        ):
            non_flag_class = "Low-volume stable"
        # 5. No risk signal (PB-6): everything else
        else:
            non_flag_class = "No risk signal"

    # Playbook assignment
    primary_pb = "PB-6"
    secondary_pbs: List[str] = []

    if flagged or non_flag_class == "Watch":
        # Sort active causes by level descending, then by TIE_ORDER
        sorted_active = sorted(
            active_causes.keys(),
            key=lambda name: (causes[name]["level"], -TIE_ORDER.index(name)),
            reverse=True,
        )
        if sorted_active:
            primary_name = sorted_active[0]
            primary_pb = CAUSE_TO_PLAYBOOK[primary_name]
            secondary_pbs = [CAUSE_TO_PLAYBOOK[n] for n in sorted_active[1:]]
    elif non_flag_class == "Growth":
        primary_pb = "PB-5"
    else:
        primary_pb = "PB-6"

    # Reason construction
    reason_parts = []
    if flagged:
        if decline_pct is not None and decline_pct >= decline_gate:
            reason_parts.append(f"TPV is {decline_pct:.1f}% below baseline average")
        # Add cause evidence in order of level desc, then TIE_ORDER
        sorted_causes = sorted(
            [name for name in causes if causes[name]["level"] >= 1],
            key=lambda name: (causes[name]["level"], -TIE_ORDER.index(name)),
            reverse=True,
        )
        for c_name in sorted_causes:
            reason_parts.append(causes[c_name]["evidence"])
        if proj_loss is not None and proj_loss <= -50.0:
            reason_parts.append(f"severe projected 90d TPV loss of {proj_loss:.1f}%")
        reason = "; ".join(reason_parts)
    elif non_flag_class == "Watch":
        watch_causes = [name for name in ["Performance", "Service", "Disengagement"] if causes[name]["level"] >= watch_min_lvl]
        ev_list = [causes[n]["evidence"] for n in watch_causes]
        reason = f"Watch tier (no TPV decline yet): {'; '.join(ev_list)}"
    elif non_flag_class == "Growth":
        reason = f"Healthy volume growth: recent 3m TPV is {growth_pct:.1f}% above baseline"
    elif non_flag_class == "Seasonal":
        reason = f"Seasonal pattern in {industry}: baseline spread <= 12%, step dip in M4, rebound of {features.get('rebound_pct', 0):.1f}% in M6"
    elif non_flag_class == "Low-volume stable":
        reason = f"Low-volume stable account: M6 TPV {tpv_m6:.2f}L (< {low_vol_limit}L) and decline {decline_pct:.1f}% (< {decline_gate}%)"
    else:
        reason = "No risk signal: metrics within normal operating bounds"

    return {
        "flagged": flagged,
        "label": label,
        "non_flag_class": non_flag_class,
        "causes": causes,
        "signal_count": signal_count,
        "top_level": top_level,
        "primary_playbook": primary_pb,
        "secondary_playbooks": secondary_pbs,
        "reason": reason,
    }
