"""
Deterministic feature calculation module for Razorpay Merchant Churn Early-Warning.
"""

from typing import Dict, Any, Optional
import math


def calculate_merchant_features(row: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes all derived deterministic features for a single merchant row.
    Returns None for any feature where required inputs are missing or invalid.
    Never exposes NaN or Inf.
    """
    m1 = row.get("tpv_m1_inr_lakh")
    m2 = row.get("tpv_m2_inr_lakh")
    m3 = row.get("tpv_m3_inr_lakh")
    m4 = row.get("tpv_m4_inr_lakh")
    m5 = row.get("tpv_m5_inr_lakh")
    m6 = row.get("tpv_m6_inr_lakh")

    sr_1_3 = row.get("success_rate_m1_m3_pct")
    sr_4_6 = row.get("success_rate_m4_m6_pct")

    # baseline = mean(m1, m2, m3) - all 3 required
    baseline: Optional[float] = None
    if m1 is not None and m2 is not None and m3 is not None:
        baseline = (m1 + m2 + m3) / 3.0

    # recent = mean(m4, m5, m6) - all 3 required
    recent: Optional[float] = None
    if m4 is not None and m5 is not None and m6 is not None:
        recent = (m4 + m5 + m6) / 3.0

    # decline_pct = (baseline - recent) / baseline * 100
    decline_pct: Optional[float] = None
    if baseline is not None and recent is not None and baseline > 0:
        decline_pct = (baseline - recent) / baseline * 100.0

    # growth_pct = (recent / baseline - 1) * 100
    growth_pct: Optional[float] = None
    if baseline is not None and recent is not None and baseline > 0:
        growth_pct = (recent / baseline - 1.0) * 100.0

    # rebound_pct = (tpv_m6 / tpv_m5 - 1) * 100
    rebound_pct: Optional[float] = None
    if m6 is not None and m5 is not None and m5 > 0:
        rebound_pct = (m6 / m5 - 1.0) * 100.0

    # m1_m3_spread = (max(m1..m3) / min(m1..m3) - 1) * 100
    m1_m3_spread: Optional[float] = None
    if m1 is not None and m2 is not None and m3 is not None:
        min_m1_m3 = min(m1, m2, m3)
        if min_m1_m3 > 0:
            m1_m3_spread = (max(m1, m2, m3) / min_m1_m3 - 1.0) * 100.0

    # step_rebound = m1_m3_spread <= 12 AND tpv_m4 <= 0.8 * baseline AND rebound_pct >= 10
    step_rebound: Optional[bool] = None
    seasonal_shape_cfg = config.get("seasonal_shape", {})
    spread_max = seasonal_shape_cfg.get("m1_m3_spread_max_pct", 12)
    m4_max_ratio = seasonal_shape_cfg.get("m4_max_of_baseline", 0.8)
    rebound_min = seasonal_shape_cfg.get("m6_rebound_min_pct", 10)

    if (
        m1_m3_spread is not None
        and baseline is not None
        and m4 is not None
        and rebound_pct is not None
    ):
        step_rebound = (
            m1_m3_spread <= spread_max
            and m4 <= m4_max_ratio * baseline
            and rebound_pct >= rebound_min
        )

    # g = (tpv_m6 / tpv_m3) ** (1/3)
    # proj_loss_90d = (tpv_m6 * g**3 / baseline - 1) * 100
    g: Optional[float] = None
    proj_loss_90d: Optional[float] = None
    if m6 is not None and m3 is not None and baseline is not None and m3 > 0 and baseline > 0:
        ratio = m6 / m3
        if ratio >= 0:
            g = ratio ** (1.0 / 3.0)
            proj_loss_90d = (m6 * (g ** 3) / baseline - 1.0) * 100.0

    # sr_drop_pts = success_rate_m1_m3_pct - success_rate_m4_m6_pct
    sr_drop_pts: Optional[float] = None
    if sr_1_3 is not None and sr_4_6 is not None:
        sr_drop_pts = sr_1_3 - sr_4_6

    # annual_value_rs = tpv_m6 * 12 * 0.01 * 100000
    net_rev_pct = config.get("net_revenue_pct", 1.0) / 100.0
    val_months = config.get("value_months", 12)
    tpv_unit = config.get("tpv_unit_rs", 100000)
    annual_value_rs: Optional[float] = None
    if m6 is not None:
        annual_value_rs = m6 * val_months * net_rev_pct * tpv_unit

    return {
        "baseline": baseline,
        "recent": recent,
        "decline_pct": decline_pct,
        "growth_pct": growth_pct,
        "rebound_pct": rebound_pct,
        "m1_m3_spread": m1_m3_spread,
        "step_rebound": step_rebound,
        "g": g,
        "proj_loss_90d": proj_loss_90d,
        "sr_drop_pts": sr_drop_pts,
        "annual_value_rs": annual_value_rs,
    }
