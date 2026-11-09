"""
Data loader and validation module for Razorpay Merchant Churn Early-Warning system.
"""

from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np


REQUIRED_SHEETS = ["P2_Merchants", "P2_Playbooks", "P2_Assumptions"]

REQUIRED_MERCHANT_COLUMNS = [
    "merchant_id",
    "business_name",
    "segment",
    "industry",
    "city",
    "tenure_months",
    "tpv_m1_inr_lakh",
    "tpv_m2_inr_lakh",
    "tpv_m3_inr_lakh",
    "tpv_m4_inr_lakh",
    "tpv_m5_inr_lakh",
    "tpv_m6_inr_lakh",
    "success_rate_m1_m3_pct",
    "success_rate_m4_m6_pct",
    "support_tickets_last_90d",
    "unresolved_tickets",
    "last_csat_1_to_5",
    "products_used",
    "logins_last_30d",
    "days_to_contract_renewal",
    "account_manager_note",
]

NUMERIC_NON_NEGATIVE_COLS = [
    "tenure_months",
    "tpv_m1_inr_lakh",
    "tpv_m2_inr_lakh",
    "tpv_m3_inr_lakh",
    "tpv_m4_inr_lakh",
    "tpv_m5_inr_lakh",
    "tpv_m6_inr_lakh",
    "success_rate_m1_m3_pct",
    "success_rate_m4_m6_pct",
    "support_tickets_last_90d",
    "unresolved_tickets",
    "products_used",
    "logins_last_30d",
    "days_to_contract_renewal",
]


DEFAULT_PLAYBOOKS = [
    {
        "playbook_id": "PB-1",
        "name": "Performance deep-dive",
        "what_happens": "Joint call with merchant and Payments Ops to review success-rate drop by method/bank; share fix plan within 3 days.",
        "when_it_applies": "Success rate fell sharply or merchant complains of failures",
    },
    {
        "playbook_id": "PB-2",
        "name": "Support recovery",
        "what_happens": "CSM takes ownership of all open tickets, gives a single point of contact and a closure date; senior callback within 48 hours.",
        "when_it_applies": "Multiple unresolved tickets, low CSAT",
    },
    {
        "playbook_id": "PB-3",
        "name": "Commercial review",
        "what_happens": "Account Manager reviews rate card, volume tiers and renewal terms before the renewal date.",
        "when_it_applies": "Competitor mention, renewal within ~60 days",
    },
    {
        "playbook_id": "PB-4",
        "name": "Re-engagement and adoption",
        "what_happens": "Executive-sponsor outreach plus a short workshop on unused products and reports; re-confirm the right contact person.",
        "when_it_applies": "Low logins, few products used, no response to outreach",
    },
    {
        "playbook_id": "PB-5",
        "name": "Growth / expansion check-in",
        "what_happens": "Positive check-in; offer new products or higher-limit plans.",
        "when_it_applies": "Healthy and growing",
    },
    {
        "playbook_id": "PB-6",
        "name": "Monitor only",
        "what_happens": "No outreach; keep on watchlist and re-check next month.",
        "when_it_applies": "Seasonal dip, low-volume stable, or no real risk signal",
    },
]

DEFAULT_ASSUMPTIONS = [
    {"item": "Net revenue", "assumption": "Razorpay earns about 1% of TPV as net revenue (assumption for this exercise)."},
    {"item": "Time horizon", "assumption": "'Churn' means the merchant moves most of its volume away within the next 90 days."},
    {"item": "Cost of a false alarm", "assumption": "1.5 hours of CSM time per outreach, valued at Rs 1,500."},
    {"item": "Value of a saved merchant", "assumption": "Net revenue for 12 months at the merchant's most recent monthly TPV (m6)."},
    {"item": "TPV unit", "assumption": "All TPV figures are in Rs lakh per month (1 lakh = 100,000)."},
    {"item": "Seasonality", "assumption": "Gifting, Education and Travel merchants have seasonal dips that are not churn."},
    {"item": "Capacity", "assumption": "The CSM team can run at most 15 proactive outreaches this month."},
]


def load_workbook(file_path_or_buffer) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Any]]:
    """
    Loads Excel workbook and validates required columns.
    Accepts workbooks with only 1 sheet (merchants) or multi-sheet data packs.
    Playbooks and Assumptions are built-in as defaults if absent.
    Returns (sheets_dict, validation_summary).
    """
    excel_file = pd.ExcelFile(file_path_or_buffer)
    sheet_names = excel_file.sheet_names

    # Locate merchants sheet: 'P2_Merchants', or first sheet if only 1 sheet exists
    if "P2_Merchants" in sheet_names:
        merchant_sheet_name = "P2_Merchants"
    elif len(sheet_names) == 1:
        merchant_sheet_name = sheet_names[0]
    else:
        # Check for sheet with 'merchant' in name
        m_sheets = [s for s in sheet_names if "merchant" in s.lower()]
        if m_sheets:
            merchant_sheet_name = m_sheets[0]
        else:
            merchant_sheet_name = sheet_names[0]

    df_merchants_raw = pd.read_excel(excel_file, sheet_name=merchant_sheet_name)

    # Use existing sheets or fallback to built-in system standards
    if "P2_Playbooks" in sheet_names:
        df_playbooks = pd.read_excel(excel_file, sheet_name="P2_Playbooks")
    else:
        df_playbooks = pd.DataFrame(DEFAULT_PLAYBOOKS)

    if "P2_Assumptions" in sheet_names:
        df_assumptions = pd.read_excel(excel_file, sheet_name="P2_Assumptions")
    else:
        df_assumptions = pd.DataFrame(DEFAULT_ASSUMPTIONS)

    missing_cols = [c for c in REQUIRED_MERCHANT_COLUMNS if c not in df_merchants_raw.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in P2_Merchants: {', '.join(missing_cols)}")

    total_rows = len(df_merchants_raw)
    
    # Process rows
    valid_rows = []
    rejected_count = 0
    column_missing_counts = {c: 0 for c in REQUIRED_MERCHANT_COLUMNS}
    blank_note_count = 0

    for idx, row in df_merchants_raw.iterrows():
        merchant_id = row.get("merchant_id")
        if pd.isna(merchant_id) or str(merchant_id).strip() == "":
            rejected_count += 1
            continue

        merchant_dict = {}
        missing_inputs = []

        # Process text columns
        for c in ["merchant_id", "business_name", "segment", "industry", "city"]:
            val = row.get(c)
            if pd.isna(val) or str(val).strip() == "":
                merchant_dict[c] = None
                missing_inputs.append(c)
                column_missing_counts[c] += 1
            else:
                merchant_dict[c] = str(val).strip()

        # Process account_manager_note
        raw_note = row.get("account_manager_note")
        if pd.isna(raw_note) or str(raw_note).strip() == "":
            merchant_dict["account_manager_note"] = None
            blank_note_count += 1
            column_missing_counts["account_manager_note"] += 1
        else:
            merchant_dict["account_manager_note"] = str(raw_note).strip()

        # Process numeric non-negative columns
        for c in NUMERIC_NON_NEGATIVE_COLS:
            val = row.get(c)
            if pd.isna(val) or val == "":
                merchant_dict[c] = None
                missing_inputs.append(c)
                column_missing_counts[c] += 1
            else:
                try:
                    num_val = float(val)
                    if num_val < 0 or np.isnan(num_val) or np.isinf(num_val):
                        merchant_dict[c] = None
                        missing_inputs.append(f"{c}(invalid:{val})")
                        column_missing_counts[c] += 1
                    else:
                        merchant_dict[c] = num_val
                except (ValueError, TypeError):
                    merchant_dict[c] = None
                    missing_inputs.append(f"{c}(non-numeric:{val})")
                    column_missing_counts[c] += 1

        # Process CSAT (1 to 5)
        csat_val = row.get("last_csat_1_to_5")
        if pd.isna(csat_val) or csat_val == "":
            merchant_dict["last_csat_1_to_5"] = None
            column_missing_counts["last_csat_1_to_5"] += 1
        else:
            try:
                num_csat = float(csat_val)
                if 1.0 <= num_csat <= 5.0 and not np.isnan(num_csat):
                    merchant_dict["last_csat_1_to_5"] = num_csat
                else:
                    merchant_dict["last_csat_1_to_5"] = None
                    missing_inputs.append(f"last_csat_1_to_5(out-of-range:{csat_val})")
                    column_missing_counts["last_csat_1_to_5"] += 1
            except (ValueError, TypeError):
                merchant_dict["last_csat_1_to_5"] = None
                missing_inputs.append(f"last_csat_1_to_5(non-numeric:{csat_val})")
                column_missing_counts["last_csat_1_to_5"] += 1

        merchant_dict["missing_inputs"] = missing_inputs
        valid_rows.append(merchant_dict)

    df_clean_merchants = pd.DataFrame(valid_rows)

    summary = {
        "total_rows": total_rows,
        "valid_rows": len(valid_rows),
        "rejected_rows": rejected_count,
        "column_missing_counts": column_missing_counts,
        "blank_note_count": blank_note_count,
    }

    sheets = {
        "P2_Merchants": df_clean_merchants,
        "P2_Playbooks": df_playbooks,
        "P2_Assumptions": df_assumptions,
    }
    return sheets, summary
