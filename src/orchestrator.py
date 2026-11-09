"""
Agent Orchestrator module.
Coordinates workbook loading, deterministic feature engineering, note classification,
human-in-the-loop confirmation, scoring, ranking, outreach drafting, and validation.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import yaml
from src.loader import load_workbook
from src.features import calculate_merchant_features
from src.note_tagger import classify_note_deterministic
from src.scoring import assess_merchant_risk
from src.ranking import rank_portfolio, calculate_renewal_urgency
from src.value_scenario import calculate_value_scenario, aggregate_drivers
from src.validator import validate_draft
from src.llm import LLMService
from src.exporter import compute_file_sha256, generate_export_dataframes, export_to_excel


class AgentOrchestrator:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self.load_config()
        self.llm_service = LLMService()

        # State storage (for session)
        self.raw_merchants_df = None
        self.summary = {}
        self.workbook_hash = ""
        self.merchants: List[Dict[str, Any]] = []
        self.portfolio: List[Dict[str, Any]] = []
        self.note_audit: List[Dict[str, Any]] = []
        self.confirmed_tags: Dict[str, Dict[str, Any]] = {}  # merchant_id -> {tag, source, confirmed}
        self.value_scenario: Dict[str, Any] = {}
        self.driver_summary: Dict[str, Any] = {}

    def load_config(self) -> Dict[str, Any]:
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def update_config(self, new_config: Dict[str, Any]):
        self.config = dict(new_config)

    def load_and_validate(self, file_path_or_buffer):
        """Loads and validates workbook, extracts clean merchant rows."""
        self.workbook_hash = compute_file_sha256(file_path_or_buffer)
        sheets, summary = load_workbook(file_path_or_buffer)
        self.raw_merchants_df = sheets["P2_Merchants"]
        self.summary = summary
        self.playbooks_df = sheets["P2_Playbooks"]
        self.assumptions_df = sheets["P2_Assumptions"]

        # Initialize base merchants with features and deterministic note tags
        merchants_list = []
        for _, row in self.raw_merchants_df.iterrows():
            m = row.to_dict()
            features = calculate_merchant_features(m, self.config)
            m.update(features)
            raw_note = m.get("account_manager_note")
            det_tag = classify_note_deterministic(raw_note, self.config)
            m["deterministic_tag"] = det_tag
            m["note_tag"] = det_tag
            m["note_tag_source"] = "deterministic"
            m["note_tag_confirmed"] = True
            merchants_list.append(m)

        self.merchants = merchants_list
        return summary

    def process_ambiguous_notes(self):
        """
        Identifies UNKNOWN notes and fetches LLM suggestions if not already done.
        Suggestions remain UNCONFIRMED until explicitly approved by the human.
        """
        audit_records = []
        for m in self.merchants:
            m_id = m.get("merchant_id")
            raw_note = m.get("account_manager_note")
            det_tag = m.get("deterministic_tag", "UNKNOWN")

            # Check if user previously confirmed a tag for this merchant
            if m_id in self.confirmed_tags:
                conf_info = self.confirmed_tags[m_id]
                m["note_tag"] = conf_info["tag"]
                m["note_tag_source"] = conf_info["source"]
                m["note_tag_confirmed"] = conf_info["confirmed"]
                audit_records.append({
                    "merchant_id": m_id,
                    "account_manager_note": raw_note,
                    "deterministic_tag": det_tag,
                    "ai_suggestion": conf_info.get("ai_suggestion", ""),
                    "evidence_phrase": conf_info.get("evidence_phrase", ""),
                    "explanation": conf_info.get("explanation", ""),
                    "confirmed_tag": conf_info["tag"],
                    "confirmation_status": "Confirmed" if conf_info["confirmed"] else "Unconfirmed",
                    "tag_source": conf_info["source"],
                })
                continue

            # If note is UNKNOWN and nonblank, consult LLM
            is_nonblank = raw_note is not None and str(raw_note).strip() not in ["", "nan"]
            if det_tag == "UNKNOWN" and is_nonblank:
                suggestion = self.llm_service.suggest_note_tag(raw_note)
                m["ai_suggestion"] = suggestion.get("tag")
                m["ai_evidence"] = suggestion.get("evidence_phrase")
                m["ai_explanation"] = suggestion.get("explanation")
                m["ai_ambiguity"] = suggestion.get("ambiguity_indicator")

                audit_records.append({
                    "merchant_id": m_id,
                    "account_manager_note": raw_note,
                    "deterministic_tag": det_tag,
                    "ai_suggestion": suggestion.get("tag"),
                    "evidence_phrase": suggestion.get("evidence_phrase"),
                    "explanation": suggestion.get("explanation"),
                    "confirmed_tag": "UNKNOWN",  # Remains UNKNOWN until confirmed
                    "confirmation_status": "Unconfirmed",
                    "tag_source": "ai_suggested_unconfirmed",
                })
            else:
                audit_records.append({
                    "merchant_id": m_id,
                    "account_manager_note": raw_note,
                    "deterministic_tag": det_tag,
                    "ai_suggestion": "",
                    "evidence_phrase": "",
                    "explanation": "",
                    "confirmed_tag": det_tag,
                    "confirmation_status": "Confirmed",
                    "tag_source": "deterministic",
                })

        self.note_audit = audit_records

    def confirm_note_tag(self, merchant_id: str, tag: str, source: str = "human_confirmed"):
        """Human explicitly confirms or modifies a note tag."""
        self.confirmed_tags[merchant_id] = {
            "tag": tag,
            "source": source,
            "confirmed": True,
        }
        for m in self.merchants:
            if m.get("merchant_id") == merchant_id:
                m["note_tag"] = tag
                m["note_tag_source"] = source
                m["note_tag_confirmed"] = True
                break

    def run_scoring_and_ranking(self, ranking_mode: Optional[str] = None):
        """
        Runs deterministic risk scoring, cause assessment, playbook selection,
        urgency evaluation, ranking, value scenario, and driver aggregation.
        """
        scored_list = []
        for m in self.merchants:
            m_copy = dict(m)
            # Re-compute features if needed
            feats = calculate_merchant_features(m_copy, self.config)
            m_copy.update(feats)
            risk = assess_merchant_risk(m_copy, feats, m_copy.get("note_tag", "UNKNOWN"), self.config)
            m_copy.update(risk)
            m_copy["urgency"] = calculate_renewal_urgency(m_copy.get("days_to_contract_renewal"), self.config)
            scored_list.append(m_copy)

        self.merchants = scored_list
        mode = ranking_mode or self.config.get("ranking_mode", "label_first")
        self.portfolio = rank_portfolio(self.merchants, self.config, mode)

        # Value & driver calculations
        self.value_scenario = calculate_value_scenario(self.portfolio, self.config)
        self.driver_summary = aggregate_drivers(self.portfolio)

    def generate_top15_drafts(self):
        """
        Generates outreach drafts ONLY for the 15 'Contact now' merchants.
        Validates drafts and allows at most 1 revision.
        """
        for m in self.portfolio:
            if m.get("status") == "Contact now":
                # Check if draft already generated / edited
                if m.get("draft_text") and m.get("draft_status") in ["Approved", "Edited"]:
                    continue

                text, status, errors, provenance = self.llm_service.generate_outreach_draft(m)
                m["draft_text"] = text
                m["draft_status"] = status
                m["draft_errors"] = errors
                m["draft_provenance"] = provenance

    def update_merchant_draft(self, merchant_id: str, new_text: str) -> Tuple[bool, List[str]]:
        """
        Updates draft with CSM manual edit and re-runs Python validation.
        """
        for m in self.portfolio:
            if m.get("merchant_id") == merchant_id:
                is_valid, errors = validate_draft(new_text, m)
                m["draft_text"] = new_text
                m["draft_errors"] = errors
                m["draft_status"] = "Edited" if is_valid else "Needs manual edit"
                return is_valid, errors
        return False, ["Merchant not found."]

    def approve_merchant_draft(self, merchant_id: str) -> Tuple[bool, str]:
        """
        Approves an outreach draft if valid and merchant is Contact now.
        """
        for m in self.portfolio:
            if m.get("merchant_id") == merchant_id:
                if m.get("status") != "Contact now":
                    return False, "Only Contact now merchants can be approved."
                is_valid, errors = validate_draft(m.get("draft_text", ""), m)
                if not is_valid:
                    return False, f"Cannot approve invalid draft: {'; '.join(errors)}"
                m["draft_status"] = "Approved"
                return True, "Draft successfully approved."
        return False, "Merchant not found."

    def get_export_bundle(self) -> Dict[str, Any]:
        """Prepares Excel and CSV exports."""
        dfs = generate_export_dataframes(
            self.portfolio,
            self.note_audit,
            self.driver_summary,
            self.value_scenario,
            self.config,
            self.workbook_hash,
        )
        excel_bytes = export_to_excel(dfs)
        return {
            "dfs": dfs,
            "excel_bytes": excel_bytes,
        }
