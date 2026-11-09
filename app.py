"""
Razorpay Merchant Churn Early-Warning System - Streamlit Decision Support Application
Single Source of Truth implementation according to Build Prompt v5.
"""

import os
import io
import copy
import yaml
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.orchestrator import AgentOrchestrator
from src.validator import validate_draft, count_sentences
from src.value_scenario import calculate_value_scenario
from src.ranking import rank_portfolio
from src.exporter import export_approved_drafts_csv

# Page configuration
st.set_page_config(
    page_title="Razorpay Churn Early-Warning | Decision Support Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom minimal styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 14px;
        border: 1px solid #e9ecef;
    }
    .badge-high { background-color: #ffe3e3; color: #c92a2a; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.85rem; }
    .badge-med { background-color: #fff3bf; color: #e67700; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.85rem; }
    .badge-low { background-color: #d3f9d8; color: #2b8a3e; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.85rem; }
    .badge-contact { background-color: #e7f5ff; color: #1864ab; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 0.85rem; }
    .badge-queued { background-color: #f1f3f5; color: #495057; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; }
    .badge-watch { background-color: #f3d9fa; color: #862e9c; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; }
    .guardrail-box {
        border-left: 4px solid #1864ab;
        background-color: #f8f9fa;
        padding: 10px 14px;
        margin-bottom: 12px;
        border-radius: 0 4px 4px 0;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_default_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def init_session():
    if "orchestrator" not in st.session_state:
        orch = AgentOrchestrator()
        default_file = "Buildathon_Student_Data_Pack.xlsx"
        if os.path.exists(default_file):
            orch.load_and_validate(default_file)
            orch.process_ambiguous_notes()
            orch.run_scoring_and_ranking()
            orch.generate_top15_drafts()
        st.session_state.orchestrator = orch
        st.session_state.dataset_source = "Built-in Data Pack"
        st.session_state.active_merchant_id = "C2088"


init_session()
orch: AgentOrchestrator = st.session_state.orchestrator

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.title("🛡️ Razorpay Early-Warning")
    st.caption("Merchant Churn Decision-Support MVP (15 Outreach Slots)")

    st.markdown("---")
    st.subheader("1. Data Source")
    data_choice = st.radio(
        "Workbook Source",
        ["Default Data Pack", "Upload Custom Excel (.xlsx)"],
        index=0 if st.session_state.dataset_source == "Built-in Data Pack" else 1,
    )

    if data_choice == "Upload Custom Excel (.xlsx)":
        uploaded_file = st.file_uploader("Upload Workbook", type=["xlsx"])
        if uploaded_file is not None:
            if st.button("Load and Analyze Uploaded File", type="primary"):
                summary = orch.load_and_validate(uploaded_file)
                orch.process_ambiguous_notes()
                orch.run_scoring_and_ranking()
                orch.generate_top15_drafts()
                st.session_state.dataset_source = "Uploaded File"
                st.success(f"Loaded {summary['valid_rows']} valid rows.")
                st.rerun()
    else:
        if st.session_state.dataset_source != "Built-in Data Pack":
            if st.button("Reload Default Data Pack"):
                orch.load_and_validate("Buildathon_Student_Data_Pack.xlsx")
                orch.process_ambiguous_notes()
                orch.run_scoring_and_ranking()
                orch.generate_top15_drafts()
                st.session_state.dataset_source = "Built-in Data Pack"
                st.rerun()

    st.markdown("---")
    st.subheader("2. Operational Settings")
    ranking_mode = st.selectbox(
        "Ranking Mode (15 Slots)",
        options=["label_first", "value_first"],
        index=0 if orch.config.get("ranking_mode") == "label_first" else 1,
        help="label_first prioritizes High risk before Medium risk. value_first prioritizes annual revenue.",
    )

    cap_slots = st.number_input("Outreach Capacity Cap", min_value=1, max_value=50, value=orch.config.get("cap", 15))

    with st.expander("Threshold Settings", expanded=False):
        decline_gate = st.slider("Decline Gate %", 5.0, 25.0, float(orch.config.get("decline_gate_pct", 10.0)), 1.0)
        sr_drop_l2 = st.slider("Success Rate Drop Level 2 (pts)", 3.0, 10.0, float(orch.config.get("performance", {}).get("sr_drop_level2", 5.0)), 0.5)
        sr_drop_l3 = st.slider("Success Rate Drop Level 3 (pts)", 6.0, 15.0, float(orch.config.get("performance", {}).get("sr_drop_level3", 8.0)), 0.5)
        unres_l2 = st.slider("Unresolved Tickets Level 2", 2, 5, int(orch.config.get("service", {}).get("unresolved_level2", 3)))
        unres_l3 = st.slider("Unresolved Tickets Level 3", 4, 10, int(orch.config.get("service", {}).get("unresolved_level3", 5)))

    if st.button("Apply Settings", type="primary"):
        new_cfg = copy.deepcopy(orch.config)
        new_cfg["ranking_mode"] = ranking_mode
        new_cfg["cap"] = cap_slots
        new_cfg["decline_gate_pct"] = decline_gate
        new_cfg["performance"]["sr_drop_level2"] = sr_drop_l2
        new_cfg["performance"]["sr_drop_level3"] = sr_drop_l3
        new_cfg["service"]["unresolved_level2"] = unres_l2
        new_cfg["service"]["unresolved_level3"] = unres_l3
        orch.update_config(new_cfg)
        orch.run_scoring_and_ranking(ranking_mode)
        orch.generate_top15_drafts()
        st.success("Settings applied!")
        st.rerun()

    if st.button("Reset to Default Settings"):
        default_cfg = get_default_config()
        orch.update_config(default_cfg)
        orch.run_scoring_and_ranking()
        orch.generate_top15_drafts()
        st.info("Reset to default config.")
        st.rerun()

    st.markdown("---")
    st.subheader("3. Ambiguous Notes (Human Gate)")
    unknown_notes = [m for m in orch.merchants if m.get("deterministic_tag") == "UNKNOWN" and m.get("account_manager_note")]
    if unknown_notes:
        st.info(f"{len(unknown_notes)} notes require review.")
        with st.expander("Review Note Suggestions", expanded=False):
            for m in unknown_notes:
                st.markdown(f"**Merchant:** `{m['merchant_id']}` ({m['business_name']})")
                st.caption(f"Note: \"{m['account_manager_note']}\"")
                ai_sugg = m.get("ai_suggestion") or "UNKNOWN"
                ai_exp = m.get("ai_explanation") or "No explanation"
                ai_ev = m.get("ai_evidence") or "None"
                st.write(f"**AI Suggestion:** `{ai_sugg}`")
                st.caption(f"Reason: {ai_exp} (Evidence: \"{ai_ev}\")")
                col_sel, col_btn = st.columns([2, 1])
                with col_sel:
                    chosen_tag = st.selectbox(
                        f"Confirm tag for {m['merchant_id']}",
                        ["UNKNOWN", "COMPETITOR", "RATE_CARD", "SERVICE_OPEN", "PERF_COMPLAINT", "DISENGAGED", "SEASONAL_EXPLAINED", "RESOLVED", "POSITIVE", "NEUTRAL"],
                        index=0 if ai_sugg not in ["COMPETITOR", "RATE_CARD", "SERVICE_OPEN", "PERF_COMPLAINT", "DISENGAGED", "SEASONAL_EXPLAINED", "RESOLVED", "POSITIVE", "NEUTRAL"] else ["UNKNOWN", "COMPETITOR", "RATE_CARD", "SERVICE_OPEN", "PERF_COMPLAINT", "DISENGAGED", "SEASONAL_EXPLAINED", "RESOLVED", "POSITIVE", "NEUTRAL"].index(ai_sugg),
                        key=f"tag_sel_{m['merchant_id']}",
                    )
                with col_btn:
                    if st.button("Confirm", key=f"btn_conf_{m['merchant_id']}"):
                        orch.confirm_note_tag(m['merchant_id'], chosen_tag, "human_confirmed")
                        orch.run_scoring_and_ranking()
                        orch.generate_top15_drafts()
                        st.success(f"Confirmed {m['merchant_id']} as {chosen_tag}")
                        st.rerun()
    else:
        st.success("All nonblank notes classified deterministically.")

    st.markdown("---")
    st.subheader("4. Exports")
    bundle = orch.get_export_bundle()
    st.download_button(
        "📥 Download Full Excel Audit (.xlsx)",
        data=bundle["excel_bytes"],
        file_name="Razorpay_EarlyWarning_Audit.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    approved_csv = export_approved_drafts_csv(orch.portfolio)
    st.download_button(
        "📥 Download Approved Drafts (.csv)",
        data=approved_csv,
        file_name="Approved_Outreach_Drafts.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ==============================================================================
# MAIN TABS / SCREENS
# ==============================================================================
tabs = st.tabs(["📊 Portfolio Overview", "✉️ Outreach Studio (15 Slots)", "🔬 Method, Scenarios & Tests"])

portfolio = orch.portfolio
flagged_merchants = [m for m in portfolio if m.get("flagged") is True]
contact_now_merchants = [m for m in portfolio if m.get("status") == "Contact now"]
queued_merchants = [m for m in portfolio if m.get("status") == "Queued"]
watch_merchants = [m for m in portfolio if m.get("status") == "Watch"]
growth_merchants = [m for m in portfolio if m.get("status") == "Growth"]

# ------------------------------------------------------------------------------
# SCREEN 1: PORTFOLIO OVERVIEW
# ------------------------------------------------------------------------------
with tabs[0]:
    st.header("Executive Portfolio Overview")
    st.caption("Rule-based risk assessment & capacity-constrained allocation (15 monthly outreach slots).")

    # KPIs
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    flagged_val = sum(m.get("annual_value_rs", 0) for m in flagged_merchants)
    top15_val = sum(m.get("annual_value_rs", 0) for m in contact_now_merchants)
    coverage_pct = (top15_val / flagged_val * 100.0) if flagged_val > 0 else 0.0
    urgent_soon = len([m for m in flagged_merchants if m.get("urgency") in ["Urgent", "Soon"]])
    data_warnings = orch.summary.get("blank_note_count", 0) + orch.summary.get("column_missing_counts", {}).get("last_csat_1_to_5", 0)

    with kpi_col1:
        st.metric("Flagged Merchants", f"{len(flagged_merchants)} / {len(portfolio)}", help="Merchants meeting operational decline gate or commercial threat.")
    with kpi_col2:
        st.metric("Outreach Slots", f"{len(contact_now_merchants)} / {orch.config.get('cap', 15)}", f"{len(queued_merchants)} Queued")
    with kpi_col3:
        st.metric("Value in Top 15", f"₹ {top15_val/100000:.2f} Lakh", f"{coverage_pct:.1f}% of Flagged")
    with kpi_col4:
        st.metric("Near Renewals (≤30d)", f"{urgent_soon}", "Urgent or Soon")
    with kpi_col5:
        st.metric("Data Quality Notes", f"{data_warnings}", "Blank notes / missing CSAT")

    st.markdown("---")

    # Filters
    st.subheader("Ranked Merchant Portfolio")
    f_col1, f_col2, f_col3, f_col4, f_col5 = st.columns(5)
    with f_col1:
        f_segment = st.selectbox("Segment", ["All", "Enterprise", "Mid", "Small"])
    with f_col2:
        f_label = st.selectbox("Risk Label", ["All", "High", "Medium", "Low"])
    with f_col3:
        f_status = st.selectbox("Status", ["All", "Contact now", "Queued", "Watch", "Growth", "Low-volume stable", "No risk signal"])
    with f_col4:
        f_pb = st.selectbox("Playbook", ["All", "PB-1", "PB-2", "PB-3", "PB-4", "PB-5", "PB-6"])
    with f_col5:
        f_urg = st.selectbox("Urgency", ["All", "Urgent", "Soon", "Upcoming", "none"])

    # Filter logic
    filtered = portfolio
    if f_segment != "All":
        filtered = [m for m in filtered if m.get("segment") == f_segment]
    if f_label != "All":
        filtered = [m for m in filtered if m.get("label") == f_label]
    if f_status != "All":
        filtered = [m for m in filtered if m.get("status") == f_status]
    if f_pb != "All":
        filtered = [m for m in filtered if m.get("primary_playbook") == f_pb]
    if f_urg != "All":
        filtered = [m for m in filtered if m.get("urgency") == f_urg]

    # Portfolio table
    display_rows = []
    for m in filtered:
        display_rows.append({
            "Rank": m.get("overall_rank"),
            "Merchant ID": m.get("merchant_id"),
            "Business Name": m.get("business_name"),
            "Segment": m.get("segment"),
            "Status": m.get("status"),
            "Label": m.get("label"),
            "Playbook": m.get("primary_playbook"),
            "Annual Value (₹)": f"₹ {m.get('annual_value_rs', 0):,.0f}",
            "Urgency": m.get("urgency"),
            "Signals": f"{m.get('signal_count')} (Top L{m.get('top_level')})",
            "Reason": m.get("reason"),
        })

    df_display = pd.DataFrame(display_rows)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Merchant Detail Inspector
    st.subheader("🔍 Merchant Diagnostic & Evidence Inspector")
    avail_ids = [m["merchant_id"] for m in portfolio]
    selected_id = st.selectbox(
        "Select Merchant to inspect:",
        avail_ids,
        index=avail_ids.index(st.session_state.active_merchant_id) if st.session_state.active_merchant_id in avail_ids else 0,
    )
    st.session_state.active_merchant_id = selected_id
    m_detail = next(m for m in portfolio if m["merchant_id"] == selected_id)

    col_d1, col_d2 = st.columns([1, 1])
    with col_d1:
        st.markdown(f"### {m_detail['business_name']} (`{m_detail['merchant_id']}`)")
        st.markdown(f"**Segment:** {m_detail.get('segment')} | **Industry:** {m_detail.get('industry')} | **City:** {m_detail.get('city')}")
        st.markdown(f"**Status:** `{m_detail.get('status')}` | **Risk Label:** `{m_detail.get('label')}` | **Playbook:** `{m_detail.get('primary_playbook')}`")
        st.markdown(f"**Annual Net Revenue at Stake (1% assumption):** ₹ {m_detail.get('annual_value_rs', 0):,.0f}")
        st.markdown(f"**Contract Renewal:** {int(m_detail.get('days_to_contract_renewal', 0))} days (`{m_detail.get('urgency')}`)")
        
        st.markdown("#### Primary Evidence & Reason")
        st.info(m_detail.get("reason"))

        st.markdown("#### Cause Signal Breakdown (Graded 0 to 3)")
        causes = m_detail.get("causes", {})
        c_table = []
        for c_name, c_info in causes.items():
            c_table.append({
                "Cause": c_name,
                "Level": f"Level {c_info.get('level')}",
                "Evidence & Values": c_info.get("evidence") or "None (rule did not fire)",
            })
        st.table(pd.DataFrame(c_table))

    with col_d2:
        st.markdown("#### 6-Month TPV Trajectory (₹ Lakh)")
        tpv_history = [
            {"Month": "M1", "TPV (Lakh)": m_detail.get("tpv_m1_inr_lakh")},
            {"Month": "M2", "TPV (Lakh)": m_detail.get("tpv_m2_inr_lakh")},
            {"Month": "M3", "TPV (Lakh)": m_detail.get("tpv_m3_inr_lakh")},
            {"Month": "M4", "TPV (Lakh)": m_detail.get("tpv_m4_inr_lakh")},
            {"Month": "M5", "TPV (Lakh)": m_detail.get("tpv_m5_inr_lakh")},
            {"Month": "M6 (Latest)", "TPV (Lakh)": m_detail.get("tpv_m6_inr_lakh")},
        ]
        df_tpv = pd.DataFrame(tpv_history)
        st.line_chart(df_tpv.set_index("Month"), height=220)

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Baseline (M1-M3)", f"{m_detail.get('baseline', 0):.2f}L")
        with col_m2:
            st.metric("Recent (M4-M6)", f"{m_detail.get('recent', 0):.2f}L")
        with col_m3:
            dec = m_detail.get("decline_pct")
            st.metric("Decline %", f"{dec:.1f}%" if dec is not None else "N/A")

        st.markdown("#### Account Note & Tag Provenance")
        raw_note = m_detail.get("account_manager_note")
        if raw_note:
            st.write(f"*\"{raw_note}\"*")
        else:
            st.caption("No account manager note recorded (Blank).")
        st.write(f"**Assigned Tag:** `{m_detail.get('note_tag')}` (Source: `{m_detail.get('note_tag_source')}`)")


# ------------------------------------------------------------------------------
# SCREEN 2: OUTREACH STUDIO
# ------------------------------------------------------------------------------
with tabs[1]:
    st.header("CSM Outreach Decision Studio")
    st.markdown("""
    <div class="guardrail-box">
        <b>Locked Outreach Guardrails (System Policy):</b><br/>
        • Strict 3–5 sentences • No discounts, waivers, or guaranteed outcomes • No deadlines or commitments<br/>
        • Never quote account notes or competitor names • Never say "churn", "at risk", "model", or mention scores/ranks<br/>
        • <b>No automated sending:</b> A human CSM must review and approve every message.
    </div>
    """, unsafe_allow_html=True)

    o_tab1, o_tab2, o_tab3, o_tab4 = st.tabs([
        f"🎯 Contact Now ({len(contact_now_merchants)} Slots)",
        f"⏳ Queued Portfolio ({len(queued_merchants)})",
        f"👁️ Watch Tier ({len(watch_merchants)})",
        f"📈 Growth Upsell ({len(growth_merchants)})",
    ])

    with o_tab1:
        st.subheader("Selected 15 Outreach Drafts")
        st.caption("Generated selectively using merchant facts and playbook guidance. Requires CSM review & approval.")

        c_now_ids = [m["merchant_id"] for m in contact_now_merchants]
        selected_draft_id = st.selectbox("Select Contact Now Merchant:", c_now_ids, key="draft_selector")
        m_draft = next(m for m in contact_now_merchants if m["merchant_id"] == selected_draft_id)

        col_dctx, col_dedit = st.columns([1, 1])

        with col_dctx:
            st.markdown(f"### {m_draft['business_name']} (`{m_draft['merchant_id']}`)")
            st.markdown(f"**Segment:** {m_draft.get('segment')} | **City:** {m_draft.get('city')}")
            st.markdown(f"**Primary Playbook:** `{m_draft.get('primary_playbook')}` ({m_draft.get('reason')})")
            st.markdown(f"**Annual Value at Stake:** ₹ {m_draft.get('annual_value_rs', 0):,.0f}")
            st.markdown(f"**Contract Renewal:** {int(m_draft.get('days_to_contract_renewal', 0))} days ({m_draft.get('urgency')})")
            st.markdown(f"**Draft Provenance:** `{m_draft.get('draft_provenance', 'Generated')}`")
            
            st.markdown("#### Key Facts for Outreach:")
            st.write(f"• Success Rate: {m_draft.get('success_rate_m1_m3_pct')}% (M1-M3) → {m_draft.get('success_rate_m4_m6_pct')}% (M4-M6)")
            st.write(f"• Unresolved Tickets: {m_draft.get('unresolved_tickets')}")
            st.write(f"• Products in Use: {m_draft.get('products_used')} | Logins Last 30d: {m_draft.get('logins_last_30d')}")

        with col_dedit:
            st.markdown("#### Outreach Draft Editor")
            current_text = m_draft.get("draft_text", "")
            current_status = m_draft.get("draft_status", "Draft")

            status_color = "#2b8a3e" if current_status == "Approved" else ("#e67700" if current_status == "Needs manual edit" else "#1864ab")
            st.markdown(f"**Status:** <span style='color:{status_color}; font-weight:700;'>{current_status}</span>", unsafe_allow_html=True)

            edited_text = st.text_area(
                "Personalized Message (3-5 sentences):",
                value=current_text,
                height=180,
                key=f"text_edit_{m_draft['merchant_id']}",
            )

            # Live sentence counter & validation
            s_count = count_sentences(edited_text)
            is_valid, val_errors = validate_draft(edited_text, m_draft)
            st.caption(f"Sentence count: **{s_count}** (Target: 3 to 5)")

            if not is_valid:
                for err in val_errors:
                    st.error(f"⚠️ {err}")
            else:
                st.success("✅ Draft passes all factual & policy guardrails.")

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("Save Edit", key=f"btn_save_{m_draft['merchant_id']}"):
                    orch.update_merchant_draft(m_draft["merchant_id"], edited_text)
                    st.success("Edit saved and revalidated.")
                    st.rerun()
            with btn_col2:
                if st.button("Approve Draft", type="primary", key=f"btn_app_{m_draft['merchant_id']}", disabled=not is_valid):
                    ok, msg = orch.approve_merchant_draft(m_draft["merchant_id"])
                    if ok:
                        st.success("Draft approved! Export in approved drafts bundle.")
                        st.rerun()
                    else:
                        st.error(msg)

    with o_tab2:
        st.subheader("Queued Portfolio (Next Month Re-check)")
        st.caption("Flagged merchants exceeding the 15-slot outreach capacity. They retain their playbook and are re-evaluated next month.")
        q_rows = []
        for m in queued_merchants:
            q_rows.append({
                "Rank": m.get("overall_rank"),
                "Merchant": m.get("merchant_id"),
                "Business Name": m.get("business_name"),
                "Segment": m.get("segment"),
                "Label": m.get("label"),
                "Playbook": m.get("primary_playbook"),
                "Annual Value (₹)": f"₹ {m.get('annual_value_rs', 0):,.0f}",
                "Urgency": m.get("urgency"),
                "Time-Critical Note": m.get("queued_note", ""),
                "Reason": m.get("reason"),
            })
        st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)

    with o_tab3:
        st.subheader("Watch Tier (Early Operational Deterioration)")
        st.caption("Merchants with operational degradation (Level ≥ 2) without TPV decline yet. They sit outside outreach slots and are re-checked next cycle.")
        if watch_merchants:
            w_rows = [{"Merchant": m["merchant_id"], "Name": m["business_name"], "Playbook": m["primary_playbook"], "Reason": m["reason"]} for m in watch_merchants]
            st.dataframe(pd.DataFrame(w_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No merchants currently in Watch Tier on the current dataset.")

    with o_tab4:
        st.subheader("Growth Upsell Portfolio (PB-5)")
        st.caption("Merchants showing healthy volume growth (recent average ≥ 15% above baseline). Outside the 15-slot churn cap.")
        st.markdown("> *No uplift value can be derived from this data, so growth outreach is a CSM judgement.*")
        g_rows = []
        for m in sorted(growth_merchants, key=lambda x: x.get("annual_value_rs", 0), reverse=True):
            g_rows.append({
                "Merchant": m.get("merchant_id"),
                "Business Name": m.get("business_name"),
                "Annual Value (₹)": f"₹ {m.get('annual_value_rs', 0):,.0f}",
                "Growth %": f"{m.get('growth_pct', 0):.1f}%",
                "Tickets": m.get("support_tickets_last_90d"),
                "CSAT": m.get("last_csat_1_to_5"),
                "Reason": m.get("reason"),
            })
        st.dataframe(pd.DataFrame(g_rows), use_container_width=True, hide_index=True)


# ------------------------------------------------------------------------------
# SCREEN 3: METHOD, SCENARIOS & TESTS
# ------------------------------------------------------------------------------
with tabs[2]:
    st.header("Methodology, Financial Scenarios & Verification")

    st.subheader("1. Three Distinct Concepts")
    st.markdown("""
    1. **Risk Label (High / Medium / Low):** Rule-based risk assessment derived deterministically from operational and commercial evidence. It is NOT a calibrated probability of churn.
    2. **Annual Value at Stake:** Estimated annual net revenue (1% net revenue assumption on Month 6 TPV). Measures financial exposure, not probability.
    3. **Selection (Contact now / Queued):** Priority allocation under a strict 15-outreach monthly constraint.
    """)

    st.markdown("---")
    st.subheader("2. Transparent Agent Workflow Architecture")
    wf_data = [
        {"Task": "Workbook Loading & Validation", "Implementation": "Python / pandas / openpyxl", "Why Deterministic": "Exact data integrity, no imputation"},
        {"Task": "Derived Features & Value", "Implementation": "Python pure functions", "Why Deterministic": "Arithmetic must be strictly reproducible"},
        {"Task": "Risk Grading, Labels & Watch Tier", "Implementation": "Python rule engine", "Why Deterministic": "Auditable thresholds and row evidence"},
        {"Task": "Playbook Assignment & Ranking", "Implementation": "Python deterministic sorting", "Why Deterministic": "Transparent tie-breaking and capacity cap"},
        {"Task": "Obvious Note Classification", "Implementation": "Python Regex Patterns", "Why Deterministic": "Instant, zero latency, no hallucination"},
        {"Task": "Ambiguous Note Tagging", "Implementation": "Selective LLM (Structured JSON)", "Human-in-the-Loop": "Mandatory CSM confirmation before scoring"},
        {"Task": "Top 15 Outreach Drafting", "Implementation": "Selective LLM with Template Fallback", "Human-in-the-Loop": "Python validator + CSM review & approval"},
        {"Task": "Sending Outreach", "Implementation": "Deliberately Not Built", "Policy": "NO message is ever sent automatically"},
    ]
    st.table(pd.DataFrame(wf_data))

    st.markdown("---")
    st.subheader("3. Selection Rationale: `label_first` vs `value_first` Top 15 Comparison")
    st.markdown("""
    `label_first` is the default because the case evaluates identifying merchants genuinely at risk under a 15-contact constraint,
    not merely maximizing rupee exposure.
    """)

    ranked_label = rank_portfolio(orch.merchants, orch.config, "label_first")
    ranked_val = rank_portfolio(orch.merchants, orch.config, "value_first")

    top15_l = [m for m in ranked_label if m.get("status") == "Contact now"]
    top15_v = [m for m in ranked_val if m.get("status") == "Contact now"]

    val_l = sum(m.get("annual_value_rs", 0) for m in top15_l)
    val_v = sum(m.get("annual_value_rs", 0) for m in top15_v)
    high_l = len([m for m in top15_l if m.get("label") == "High"])
    high_v = len([m for m in top15_v if m.get("label") == "High"])

    cmp_col1, cmp_col2 = st.columns(2)
    with cmp_col1:
        st.markdown("#### Default: `label_first`")
        st.write(f"• High-Risk Selected: **{high_l} / 12**")
        st.write(f"• Annual Value Represented: **₹ {val_l:,.0f}** ({val_l/100000:.2f}L)")
        st.caption("Selected IDs: " + ", ".join([m["merchant_id"] for m in top15_l]))

    with cmp_col2:
        st.markdown("#### Alternative: `value_first`")
        st.write(f"• High-Risk Selected: **{high_v} / 12** (leaves 7 High merchants in queue)")
        st.write(f"• Annual Value Represented: **₹ {val_v:,.0f}** ({val_v/100000:.2f}L)")
        st.caption("Selected IDs: " + ", ".join([m["merchant_id"] for m in top15_v]))

    set_l = set(m["merchant_id"] for m in top15_l)
    set_v = set(m["merchant_id"] for m in top15_v)
    in_l_only = sorted(list(set_l - set_v))
    in_v_only = sorted(list(set_v - set_l))
    st.info(f"**Merchants in `label_first` only:** {', '.join(in_l_only)} (Severe operational deterioration e.g. C2001, C2015, C2034 with >8pt SR drop)\n\n**Merchants in `value_first` only:** {', '.join(in_v_only)}")

    st.markdown("---")
    st.subheader("4. Financial Value Scenario (Scenario, Not Forecast)")
    st.markdown("> **Scenario, not forecast:** Likelihood and save rate are illustrative sensitivity assumptions, not historical model forecasts.")

    sc_col1, sc_col2 = st.columns(2)
    with sc_col1:
        s_likelihood = st.slider("Assumed Churn Likelihood", 0.0, 1.0, 0.75, 0.05)
    with sc_col2:
        s_save_rate = st.slider("Assumed Outreach Save Rate", 0.0, 1.0, 0.25, 0.05)

    scenario_res = calculate_value_scenario(portfolio, orch.config, s_likelihood, s_save_rate)
    st.write(f"• **Value at Stake (Contact now):** ₹ {scenario_res['value_at_stake_rs']:,.0f}")
    st.write(f"• **Assumed Outreach Cost:** ₹ {scenario_res['total_cost_rs']:,.0f} (₹ 1,500 assumed cost per outreach)")
    st.write(f"• **Net Financial Value:** ₹ {scenario_res['net_value_rs']:,.0f}")
    be_str = f"{scenario_res['break_even_save_pct']:.3f}%" if scenario_res['break_even_save_pct'] is not None else "Not Applicable (Zero Likelihood/Value)"
    st.write(f"• **Break-Even Save Rate:** **{be_str}**")

    st.markdown("---")
    st.subheader("5. Key Drivers & Static Operational Fixes")
    driver_data = orch.driver_summary.get("drivers", [])
    st.table(pd.DataFrame(driver_data))
    largest = orch.driver_summary.get("largest_driver")
    if largest:
        st.markdown(f"**Largest Risk Driver:** {largest['name']} (₹ {largest['annual_value_at_stake']:,.0f} at stake)")
        st.info(f"**Static Process Recommendation:** {orch.driver_summary.get('suggested_fix')}")

    st.markdown("---")
    st.subheader("6. Honest System Limitations (Section 12)")
    st.markdown("""
    - **No Hidden Labels:** No churn labels exist; results cannot be claimed as predictive accuracy. Thresholds are judgement defaults.
    - **Commercial Risk Visibility:** Commercial threats are visible exclusively through notes. Blank notes have no commercial signal.
    - **Weak Commercial Signal:** Rate-card requests alone can flag a merchant but never cause High risk alone.
    - **Seasonality Approximations:** Seasonal detection uses industry and step-rebound shape; multi-year YoY data would be preferable.
    - **Watch Tier Untested:** The provided synthetic Data Pack has zero Watch merchants; tier logic is verified via unit tests.
    """)

    st.markdown("---")
    st.subheader("7. Design-History Failure Log (Section 16)")
    st.markdown("""
    1. Early seasonal-shape test missed C2066 because flat spread was 8%; loosened to 12%.
    2. Early version required falling TPV for commercial threats, missing C2004, C2022, C2036; fixed by flagging commercial intent near renewal without TPV decline.
    3. Non-pricing note scored as 0 commercial risk lowered overall score (62.2 vs 73.1); fixed by treating it as unknown, leading to removing artificial numeric score.
    4. Severe projected loss alone initially flagged High; fixed so High/Medium strictly requires meeting flag gate.
    5. Pure value ranking left 7 of 12 High merchants uncontacted; `label_first` introduced as default.
    6. ₹1,500 cost initially treated as false-alarm cost only; updated to apply to every outreach.
    7. Reason lookup bug attached mismatched facts; fixed and locked with row-invariant assertion.
    8. Early note matcher tagged "UPI issue, now resolved" as open complaint; fixed with resolved check.
    """)
