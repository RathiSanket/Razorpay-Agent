"""
Comprehensive test suite verifying Section 11 specifications:
Unit tests, Golden snapshots, Invariants, and Robustness checks.
"""

import pytest
import yaml
import copy
import random
from src.loader import load_workbook
from src.features import calculate_merchant_features
from src.note_tagger import classify_note_deterministic
from src.scoring import assess_merchant_risk, grade_causes
from src.ranking import rank_portfolio, calculate_renewal_urgency
from src.value_scenario import calculate_value_scenario, aggregate_drivers
from src.validator import validate_draft
from src.orchestrator import AgentOrchestrator


@pytest.fixture
def config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture
def base_merchant():
    return {
        "merchant_id": "M_TEST",
        "business_name": "Acme Retail",
        "segment": "Mid",
        "industry": "Ecommerce",
        "city": "Bengaluru",
        "tenure_months": 24,
        "tpv_m1_inr_lakh": 50.0,
        "tpv_m2_inr_lakh": 50.0,
        "tpv_m3_inr_lakh": 50.0,
        "tpv_m4_inr_lakh": 50.0,
        "tpv_m5_inr_lakh": 50.0,
        "tpv_m6_inr_lakh": 50.0,
        "success_rate_m1_m3_pct": 95.0,
        "success_rate_m4_m6_pct": 95.0,
        "support_tickets_last_90d": 1,
        "unresolved_tickets": 0,
        "last_csat_1_to_5": 4.5,
        "products_used": 4,
        "logins_last_30d": 15,
        "days_to_contract_renewal": 120,
        "account_manager_note": None,
    }


# ==============================================================================
# 1. Threshold Boundary Unit Tests
# ==============================================================================

def test_unresolved_ticket_threshold_boundaries(base_merchant, config):
    # Unresolved: 0 -> Level 0
    # 1 -> Level 0 (unless csat/tickets or note)
    # 2 -> Level 1
    # 3 -> Level 2
    # 4 -> Level 2
    # 5 -> Level 3
    base_merchant["support_tickets_last_90d"] = 1
    base_merchant["last_csat_1_to_5"] = 4.0

    for tickets, expected_lvl in [(0, 0), (1, 0), (2, 1), (3, 2), (4, 2), (5, 3), (6, 3)]:
        m = copy.deepcopy(base_merchant)
        m["unresolved_tickets"] = tickets
        feats = calculate_merchant_features(m, config)
        causes = grade_causes(m, feats, "BLANK", config)
        assert causes["Service"]["level"] == expected_lvl, f"Failed for unresolved={tickets}"


def test_success_rate_drop_boundaries(base_merchant, config):
    # Level 2 threshold is 5.0, Level 3 is 8.0
    for drop, expected_lvl in [(4.9, 0), (5.0, 2), (7.9, 2), (8.0, 3), (12.0, 3)]:
        m = copy.deepcopy(base_merchant)
        m["success_rate_m1_m3_pct"] = 90.0
        m["success_rate_m4_m6_pct"] = 90.0 - drop
        feats = calculate_merchant_features(m, config)
        causes = grade_causes(m, feats, "BLANK", config)
        assert causes["Performance"]["level"] == expected_lvl, f"Failed for drop={drop}"


# ==============================================================================
# 2. Zero & Missing Value Handling Tests
# ==============================================================================

def test_zero_and_missing_values_do_not_crash_or_impute(base_merchant, config):
    # Zero baseline
    m = copy.deepcopy(base_merchant)
    m["tpv_m1_inr_lakh"] = 0.0
    m["tpv_m2_inr_lakh"] = 0.0
    m["tpv_m3_inr_lakh"] = 0.0
    feats = calculate_merchant_features(m, config)
    assert feats["baseline"] == 0.0
    assert feats["decline_pct"] is None  # Avoid division by zero
    assert feats["m1_m3_spread"] is None

    # Missing required TPV month does not create partial mean
    m2 = copy.deepcopy(base_merchant)
    m2["tpv_m2_inr_lakh"] = None
    feats2 = calculate_merchant_features(m2, config)
    assert feats2["baseline"] is None
    assert feats2["decline_pct"] is None

    # Missing values never satisfy a threshold
    m3 = copy.deepcopy(base_merchant)
    m3["unresolved_tickets"] = None
    m3["logins_last_30d"] = None
    m3["days_to_contract_renewal"] = None
    feats3 = calculate_merchant_features(m3, config)
    causes3 = grade_causes(m3, feats3, "BLANK", config)
    assert causes3["Service"]["level"] == 0
    assert causes3["Disengagement"]["level"] == 0
    assert causes3["Commercial"]["level"] == 0


# ==============================================================================
# 3. Note Tagger Edge Cases
# ==============================================================================

def test_note_tagger_edge_cases(config):
    # 1. “UPI issue last month, now resolved” => RESOLVED
    note1 = "UPI issue last month, now resolved"
    assert classify_note_deterministic(note1, config) == "RESOLVED"

    # 2. “Complained about delays, fixed; but still no response to follow-ups” => DISENGAGED (no response)
    note2 = "Complained about delays, fixed; but still no response to follow-ups"
    assert classify_note_deterministic(note2, config) == "DISENGAGED"

    # 3. “UPI issue fixed; separately, comparing quotes from two providers” => COMPETITOR
    note3 = "UPI issue fixed; separately, comparing quotes from two providers"
    assert classify_note_deterministic(note3, config) == "COMPETITOR"

    # 4. “UPI fixed, but support replies take too long” => SERVICE_OPEN
    note4 = "UPI fixed, but support replies take too long"
    assert classify_note_deterministic(note4, config) == "SERVICE_OPEN"

    # 5. Unseen note with no keywords => UNKNOWN
    note5 = "Spoke with finance team regarding quarterly accounting reconciliation."
    assert classify_note_deterministic(note5, config) == "UNKNOWN"

    # Blank note => BLANK
    assert classify_note_deterministic("", config) == "BLANK"
    assert classify_note_deterministic(None, config) == "BLANK"


# ==============================================================================
# 4. Watch Tier & Label Tests
# ==============================================================================

def test_watch_tier_conditions(base_merchant, config):
    # SR deterioration >= 5 without TPV decline => Watch
    m = copy.deepcopy(base_merchant)
    m["success_rate_m1_m3_pct"] = 95.0
    m["success_rate_m4_m6_pct"] = 89.0  # drop 6.0 >= 5 (level 2)
    feats = calculate_merchant_features(m, config)
    risk = assess_merchant_risk(m, feats, "BLANK", config)
    assert not risk["flagged"]
    assert risk["label"] == "Low"
    assert risk["non_flag_class"] == "Watch"

    # 3 unresolved tickets without TPV decline => Watch
    m2 = copy.deepcopy(base_merchant)
    m2["unresolved_tickets"] = 3  # level 2
    feats2 = calculate_merchant_features(m2, config)
    risk2 = assess_merchant_risk(m2, feats2, "BLANK", config)
    assert not risk2["flagged"]
    assert risk2["label"] == "Low"
    assert risk2["non_flag_class"] == "Watch"

    # Watch never consumes a slot
    portfolio = rank_portfolio([risk, risk2], config)
    for p in portfolio:
        assert p["status"] == "Watch"


def test_severe_projected_loss_on_unflagged_stays_low(base_merchant, config):
    # An unflagged merchant with severe projected loss remains Low
    m = copy.deepcopy(base_merchant)
    # No operational cause level >= 1 and no commercial
    feats = calculate_merchant_features(m, config)
    feats["proj_loss_90d"] = -75.0  # severe loss
    risk = assess_merchant_risk(m, feats, "BLANK", config)
    assert not risk["flagged"]
    assert risk["label"] == "Low"


# ==============================================================================
# 5. Ranking & Tie-Break Tests
# ==============================================================================

def test_ranking_tie_breaks(config):
    m1 = {
        "merchant_id": "C2091",
        "business_name": "Merchant 1",
        "flagged": True,
        "label": "High",
        "annual_value_rs": 500000.0,
        "days_to_contract_renewal": 45,  # Upcoming
        "urgency": "Upcoming",
    }
    m2 = {
        "merchant_id": "C2092",
        "business_name": "Merchant 2",
        "flagged": True,
        "label": "High",
        "annual_value_rs": 500000.0,
        "days_to_contract_renewal": 20,  # Soon (wins over Upcoming)
        "urgency": "Soon",
    }
    ranked = rank_portfolio([m1, m2], config, "value_first")
    assert ranked[0]["merchant_id"] == "C2092"
    assert ranked[1]["merchant_id"] == "C2091"


# ==============================================================================
# 6. Value Panel Tests
# ==============================================================================

def test_value_panel_zero_likelihood_break_even(config):
    portfolio = [
        {"status": "Contact now", "annual_value_rs": 500000.0},
    ]
    res = calculate_value_scenario(portfolio, config, churn_likelihood=0.0, save_rate=0.25)
    assert res["break_even_save_pct"] is None


# ==============================================================================
# 7. Draft Validator Tests
# ==============================================================================

def test_draft_validator(base_merchant):
    base_merchant["business_name"] = "Acme Global"
    base_merchant["success_rate_m1_m3_pct"] = 92.5
    base_merchant["success_rate_m4_m6_pct"] = 84.1

    # Valid draft (3 sentences, correct name, facts, no banned words)
    valid_text = (
        "Dear Acme Global team, we noticed your payment success rate moved from 92.5% to 84.1% recently. "
        "Our payments operations team would like to review performance across specific methods and banks. "
        "Could we schedule a brief 15-minute call this week to share our findings and assist your team?"
    )
    is_valid, errors = validate_draft(valid_text, base_merchant)
    assert is_valid, f"Validation failed unexpectedly: {errors}"

    # Invalid: Banned phrase ('guaranteed' / 'discount')
    bad_text = (
        "Dear Acme Global team, we guarantee a 20% discount on your fees. "
        "Our team will fix all issues immediately without delay. "
        "Let us connect for 15 minutes this week."
    )
    is_val, errs = validate_draft(bad_text, base_merchant)
    assert not is_val
    assert any("discount" in e.lower() or "guarantee" in e.lower() for e in errs)

    # Invalid: Too few sentences (2 sentences)
    short_text = "Dear Acme Global team, we wanted to check in. Let us connect for 15 minutes."
    is_val2, errs2 = validate_draft(short_text, base_merchant)
    assert not is_val2
    assert any("sentences" in e.lower() for e in errs2)

    # Invalid: Missing correct business name
    no_name_text = (
        "Dear Partner team, we noticed your payment success rate moved from 92.5% to 84.1% recently. "
        "Our payments operations team would like to review performance across specific methods and banks. "
        "Could we schedule a brief 15-minute call this week to share our findings?"
    )
    is_val3, errs3 = validate_draft(no_name_text, base_merchant)
    assert not is_val3
    assert any("business name" in e.lower() for e in errs3)


# ==============================================================================
# 8. Golden Snapshot on Provided Data Pack (Section 11.2)
# ==============================================================================

def test_golden_snapshot_data_pack(config):
    sheets, summary = load_workbook("Buildathon_Student_Data_Pack.xlsx")
    df = sheets["P2_Merchants"]
    assert len(df) == 100

    merchants = []
    for _, row in df.iterrows():
        m = row.to_dict()
        feats = calculate_merchant_features(m, config)
        m.update(feats)
        tag = classify_note_deterministic(m.get("account_manager_note"), config)
        m["note_tag"] = tag
        risk = assess_merchant_risk(m, feats, tag, config)
        m.update(risk)
        m["urgency"] = calculate_renewal_urgency(m.get("days_to_contract_renewal"), config)
        merchants.append(m)

    # 1. 24 flagged: 12 High, 12 Medium; 76 Low
    flagged = [m for m in merchants if m["flagged"]]
    assert len(flagged) == 24
    assert len([m for m in merchants if m["label"] == "High"]) == 12
    assert len([m for m in merchants if m["label"] == "Medium"]) == 12
    assert len([m for m in merchants if m["label"] == "Low"]) == 76

    # 2. Non-flagged classes: 43 no-signal, 19 low-volume stable, 8 seasonal, 6 growth, 0 Watch
    unflagged = [m for m in merchants if not m["flagged"]]
    assert len(unflagged) == 76
    assert len([m for m in unflagged if m["non_flag_class"] == "No risk signal"]) == 43
    assert len([m for m in unflagged if m["non_flag_class"] == "Low-volume stable"]) == 19
    assert len([m for m in unflagged if m["non_flag_class"] == "Seasonal"]) == 8
    assert len([m for m in unflagged if m["non_flag_class"] == "Growth"]) == 6
    assert len([m for m in unflagged if m["non_flag_class"] == "Watch"]) == 0

    # 3. Seasonal IDs
    expected_seasonal = ["C2012", "C2023", "C2048", "C2054", "C2065", "C2066", "C2067", "C2094"]
    actual_seasonal = sorted([m["merchant_id"] for m in unflagged if m["non_flag_class"] == "Seasonal"])
    assert actual_seasonal == expected_seasonal

    # 4. Growth IDs in order
    expected_growth = ["C2003", "C2083", "C2072", "C2043", "C2016", "C2078"]
    growth_list = [m for m in unflagged if m["non_flag_class"] == "Growth"]
    actual_growth = [m["merchant_id"] for m in sorted(growth_list, key=lambda x: x["annual_value_rs"], reverse=True)]
    assert actual_growth == expected_growth

    # 5. label_first top 15
    expected_label_top15 = [
        "C2088", "C2090", "C2097", "C2100", "C2061", "C2032", "C2034", "C2015",
        "C2001", "C2008", "C2045", "C2020", "C2004", "C2018", "C2079"
    ]
    ranked_label = rank_portfolio(merchants, config, "label_first")
    actual_label_top15 = [m["merchant_id"] for m in ranked_label if m["status"] == "Contact now"]
    assert actual_label_top15 == expected_label_top15

    # 6. value_first top 15
    expected_val_top15 = [
        "C2004", "C2088", "C2018", "C2090", "C2079", "C2097", "C2027", "C2062",
        "C2100", "C2093", "C2061", "C2084", "C2022", "C2036", "C2092"
    ]
    ranked_val = rank_portfolio(merchants, config, "value_first")
    actual_val_top15 = [m["merchant_id"] for m in ranked_val if m["status"] == "Contact now"]
    assert actual_val_top15 == expected_val_top15

    # 7. Value panel for value_first
    val_scenario = calculate_value_scenario(ranked_val, config)
    assert pytest.approx(val_scenario["net_value_rs"] / 100000.0, 0.1) == 15.5
    assert pytest.approx(val_scenario["break_even_save_pct"], 0.05) == 0.36


# ==============================================================================
# 9. Invariants (Section 11.3)
# ==============================================================================

def test_invariants_on_data_pack(config):
    sheets, _ = load_workbook("Buildathon_Student_Data_Pack.xlsx")
    orch = AgentOrchestrator()
    orch.load_and_validate("Buildathon_Student_Data_Pack.xlsx")
    orch.process_ambiguous_notes()
    orch.run_scoring_and_ranking("label_first")
    orch.generate_top15_drafts()

    for m in orch.portfolio:
        # No Seasonal or Growth merchant is flagged
        if m.get("non_flag_class") in ["Seasonal", "Growth"]:
            assert not m.get("flagged")

        # High or Medium implies flagged
        if m.get("label") in ["High", "Medium"]:
            assert m.get("flagged") is True

        # Queued merchants never carry PB-6
        if m.get("status") == "Queued":
            assert m.get("primary_playbook") != "PB-6"

        # Check drafts for Contact now
        if m.get("status") == "Contact now":
            draft = m.get("draft_text")
            assert draft is not None
            is_valid, errors = validate_draft(draft, m)
            # If draft fails validation, it must NOT be approvable
            if not is_valid:
                ok, msg = orch.approve_merchant_draft(m["merchant_id"])
                assert not ok

    contacted_count = len([m for m in orch.portfolio if m.get("status") == "Contact now"])
    assert contacted_count <= 15
    assert contacted_count <= len([m for m in orch.portfolio if m.get("flagged")])


# ==============================================================================
# 10. Robustness Checks (Section 11.4)
# ==============================================================================

def test_robustness_notes_removed(config):
    # Blank every note. Expected: 18 of 24 still flagged; the 6 lost are the commercial group
    sheets, _ = load_workbook("Buildathon_Student_Data_Pack.xlsx")
    df = sheets["P2_Merchants"]

    flagged_ids = []
    for _, row in df.iterrows():
        m = row.to_dict()
        m["account_manager_note"] = None  # blank
        feats = calculate_merchant_features(m, config)
        m.update(feats)
        tag = classify_note_deterministic(None, config)
        m["note_tag"] = tag
        risk = assess_merchant_risk(m, feats, tag, config)
        if risk["flagged"]:
            flagged_ids.append(m["merchant_id"])

    assert len(flagged_ids) == 18
    lost_ids = sorted(list(set([
        "C2088", "C2090", "C2097", "C2100", "C2061", "C2032", "C2034", "C2015",
        "C2001", "C2008", "C2045", "C2020", "C2004", "C2018", "C2079",
        "C2027", "C2062", "C2093", "C2084", "C2022", "C2036", "C2092", "C2040", "C2091"
    ]) - set(flagged_ids)))
    expected_lost = sorted(["C2004", "C2018", "C2022", "C2036", "C2040", "C2092"])
    assert lost_ids == expected_lost


def test_transformed_workbook_smoke_test(config):
    # (a) Keep a seeded random 60 rows
    # (b) Rename merchant IDs
    # (c) Blank 10% of random cells
    sheets, _ = load_workbook("Buildathon_Student_Data_Pack.xlsx")
    df = sheets["P2_Merchants"]

    random.seed(42)
    sample_indices = random.sample(range(len(df)), 60)
    sampled_rows = []

    for new_idx, orig_idx in enumerate(sample_indices):
        row = df.iloc[orig_idx].to_dict()
        row["merchant_id"] = f"SYNTH_{new_idx:03d}"
        # Blank 10% of data columns randomly
        for col in ["tpv_m1_inr_lakh", "tpv_m4_inr_lakh", "success_rate_m4_m6_pct", "unresolved_tickets", "logins_last_30d"]:
            if random.random() < 0.10:
                row[col] = None
        sampled_rows.append(row)

    # Run full engine
    merchants = []
    for r in sampled_rows:
        feats = calculate_merchant_features(r, config)
        r.update(feats)
        tag = classify_note_deterministic(r.get("account_manager_note"), config)
        r["note_tag"] = tag
        risk = assess_merchant_risk(r, feats, tag, config)
        r.update(risk)
        r["urgency"] = calculate_renewal_urgency(r.get("days_to_contract_renewal"), config)
        merchants.append(r)

    ranked = rank_portfolio(merchants, config, "label_first")
    assert len(ranked) == 60
    contact_count = len([m for m in ranked if m["status"] == "Contact now"])
    assert contact_count <= 15
