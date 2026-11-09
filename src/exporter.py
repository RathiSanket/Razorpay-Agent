"""
Export module for Excel and CSV formats according to Section 10 specifications.
"""

from typing import Dict, Any, List, Optional
import io
import hashlib
import json
import pandas as pd


def compute_file_sha256(file_path_or_bytes) -> str:
    """Computes SHA-256 hash of workbook."""
    sha256 = hashlib.sha256()
    if isinstance(file_path_or_bytes, (str, bytes)):
        if isinstance(file_path_or_bytes, str):
            with open(file_path_or_bytes, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
        else:
            sha256.update(file_path_or_bytes)
    elif hasattr(file_path_or_bytes, "read"):
        file_path_or_bytes.seek(0)
        while chunk := file_path_or_bytes.read(8192):
            sha256.update(chunk)
        file_path_or_bytes.seek(0)
    return sha256.hexdigest()


def generate_export_dataframes(
    portfolio: List[Dict[str, Any]],
    note_audit: List[Dict[str, Any]],
    driver_summary: Dict[str, Any],
    value_scenario: Dict[str, Any],
    config: Dict[str, Any],
    workbook_hash: str = "",
) -> Dict[str, pd.DataFrame]:
    """
    Constructs dataframes for all export sheets.
    """
    # 1. Ranked_All
    ranked_all_rows = []
    for m in portfolio:
        sec_pb_str = ", ".join(m.get("secondary_playbooks", []))
        missing_inp_str = ", ".join(m.get("missing_inputs", []))
        ranked_all_rows.append({
            "overall_rank": m.get("overall_rank"),
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "segment": m.get("segment"),
            "status": m.get("status"),
            "label": m.get("label"),
            "signal_count": m.get("signal_count"),
            "top_level": m.get("top_level"),
            "primary_playbook": m.get("primary_playbook"),
            "secondary_playbooks": sec_pb_str,
            "annual_value_rs": m.get("annual_value_rs"),
            "urgency": m.get("urgency"),
            "reason": m.get("reason"),
            "missing_inputs": missing_inp_str,
            "note_tag": m.get("note_tag"),
            "note_tag_source": m.get("note_tag_source", "deterministic"),
            "note_tag_confirmed": m.get("note_tag_confirmed", True),
        })
    df_ranked_all = pd.DataFrame(ranked_all_rows)

    # 2. Top15_Outreach
    contact_now_merchants = [m for m in portfolio if m.get("status") == "Contact now"]
    top15_rows = []
    for m in contact_now_merchants:
        sec_pb_str = ", ".join(m.get("secondary_playbooks", []))
        missing_inp_str = ", ".join(m.get("missing_inputs", []))
        top15_rows.append({
            "overall_rank": m.get("overall_rank"),
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "segment": m.get("segment"),
            "status": m.get("status"),
            "label": m.get("label"),
            "signal_count": m.get("signal_count"),
            "top_level": m.get("top_level"),
            "primary_playbook": m.get("primary_playbook"),
            "secondary_playbooks": sec_pb_str,
            "annual_value_rs": m.get("annual_value_rs"),
            "urgency": m.get("urgency"),
            "reason": m.get("reason"),
            "missing_inputs": missing_inp_str,
            "note_tag": m.get("note_tag"),
            "note_tag_source": m.get("note_tag_source", "deterministic"),
            "note_tag_confirmed": m.get("note_tag_confirmed", True),
            "draft_text": m.get("draft_text", ""),
            "draft_status": m.get("draft_status", "Draft"),
            "contact_outcome": "",
            "churned_within_90d": "",
        })
    df_top15 = pd.DataFrame(top15_rows)

    # 3. Queued
    queued_merchants = [m for m in portfolio if m.get("status") == "Queued"]
    queued_rows = []
    for m in queued_merchants:
        queued_rows.append({
            "overall_rank": m.get("overall_rank"),
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "segment": m.get("segment"),
            "status": m.get("status"),
            "label": m.get("label"),
            "annual_value_rs": m.get("annual_value_rs"),
            "urgency": m.get("urgency"),
            "primary_playbook": m.get("primary_playbook"),
            "reason": m.get("reason"),
            "queued_note": m.get("queued_note", ""),
        })
    df_queued = pd.DataFrame(queued_rows)

    # 4. Watch_Growth
    wg_merchants = [m for m in portfolio if m.get("status") in ["Watch", "Growth"]]
    wg_rows = []
    for m in wg_merchants:
        wg_rows.append({
            "overall_rank": m.get("overall_rank"),
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "segment": m.get("segment"),
            "status": m.get("status"),
            "annual_value_rs": m.get("annual_value_rs"),
            "growth_pct": m.get("growth_pct"),
            "primary_playbook": m.get("primary_playbook"),
            "reason": m.get("reason"),
        })
    df_wg = pd.DataFrame(wg_rows)

    # 5. Drivers_Value
    drivers_data = driver_summary.get("drivers", [])
    df_drivers = pd.DataFrame(drivers_data)
    # Add scenario summary rows
    scenario_row = pd.DataFrame([{
        "playbook_id": "SCENARIO_SUMMARY",
        "name": f"Value at Stake: Rs {value_scenario.get('value_at_stake_rs', 0):,.0f} | Net: Rs {value_scenario.get('net_value_rs', 0):,.0f}",
        "flagged_count": value_scenario.get("contacted_count", 0),
        "annual_value_at_stake": value_scenario.get("value_at_stake_rs", 0),
        "contact_now_count": value_scenario.get("contacted_count", 0),
    }])
    df_drivers_value = pd.concat([df_drivers, scenario_row], ignore_index=True)

    # 6. Config
    config_rows = [
        {"setting": "workbook_sha256", "value": workbook_hash},
    ]
    for k, v in config.items():
        config_rows.append({"setting": k, "value": json.dumps(v) if isinstance(v, (dict, list)) else str(v)})
    df_config = pd.DataFrame(config_rows)

    # 7. Note_Tag_Audit
    df_audit = pd.DataFrame(note_audit)

    return {
        "Ranked_All": df_ranked_all,
        "Top15_Outreach": df_top15,
        "Queued": df_queued,
        "Watch_Growth": df_wg,
        "Drivers_Value": df_drivers_value,
        "Config": df_config,
        "Note_Tag_Audit": df_audit,
    }


def export_to_excel(dfs: Dict[str, pd.DataFrame]) -> bytes:
    """Exports all sheets into an Excel workbook byte stream."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.getvalue()


def export_approved_drafts_csv(portfolio: List[Dict[str, Any]]) -> str:
    """Exports approved drafts only as CSV."""
    approved = [m for m in portfolio if m.get("draft_status") == "Approved"]
    rows = []
    for m in approved:
        rows.append({
            "merchant_id": m.get("merchant_id"),
            "business_name": m.get("business_name"),
            "primary_playbook": m.get("primary_playbook"),
            "draft_text": m.get("draft_text", ""),
            "draft_status": "Approved",
            "contact_outcome": "",
            "churned_within_90d": "",
        })
    df_app = pd.DataFrame(rows)
    return df_app.to_csv(index=False)
