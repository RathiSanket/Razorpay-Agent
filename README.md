# Razorpay Merchant Churn Early-Warning Agent
### Decision Support System for CSM Leads (15 Monthly Outreach Slots)

This repository contains the competition-ready MVP built for **Razorpay Campus AI Build-a-thon — Problem 2: Merchant Churn Early-Warning**, adhering strictly to the **Build Prompt v5** specification as the single source of truth.

---

## 🚀 Quickstart Guide

### 1. Environment Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration & API Keys (Optional)
The application is **100% operational without an LLM API key**, using deterministic rule-based classifications and compliant fallback templates:
```bash
cp .env.example .env
# (Optional) Add your GEMINI_API_KEY or OPENAI_API_KEY to .env
```

### 3. Run the Streamlit Application
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

### 4. Run Test Suite
```bash
pytest tests/test_engine.py -v
```

---

## 🏛️ System Architecture: Minimal & Deterministic-First

The system uses **one lightweight Python Orchestrator** owning workflow state and auditable execution. LangGraph or multi-agent bloat is deliberately omitted.

```
                  ┌──────────────────────────────────────┐
                  │   Data Pack / Uploaded Workbook      │
                  └──────────────────┬───────────────────┘
                                     │
                                     ▼
        ┌────────────────────────────────────────────────────────┐
        │  Deterministic Python Core (pandas / openpyxl / regex)  │
        │  - Feature Engineering (TPV baseline, recent, spread)  │
        │  - Deterministic Note Tagger & Precedence Rules        │
        │  - Cause Grading (PB-1 to PB-4, Levels 0-3)            │
        │  - Flag & Risk Labels (High / Medium / Low)            │
        │  - Watch Tier & Non-Flag Classes (Growth, Seasonal)    │
        │  - Ranking & 15-Slot Allocation (label_first / value)  │
        └──────────────┬──────────────────────────┬──────────────┘
                       │                          │
        (Ambiguous     │                          │ (Contact Now
         Notes Only)   │                          │  Top 15 Only)
                       ▼                          ▼
        ┌─────────────────────────┐  ┌─────────────────────────┐
        │ Selective LLM Note Tagger│  │ Selective LLM Outreach   │
        │ (Structured JSON)       │  │ (3-5 sentences, facts)   │
        └──────────────┬──────────┘  └────────────┬────────────┘
                       │                          │
                       ▼                          ▼
        ┌─────────────────────────┐  ┌─────────────────────────┐
        │ Human CSM Confirmation  │  │ Python Draft Validator  │
        │ (Required before scoring│  │ (Max 1 Revision if fail)│
        └─────────────────────────┘  └────────────┬────────────┘
                                                  │
                                                  ▼
                                     ┌─────────────────────────┐
                                     │ CSM Review & Approval   │
                                     │ (NO automated send)     │
                                     └─────────────────────────┘
```

### Division of Responsibilities
| Task | Implementation | Why |
|---|---|---|
| **Workbook Loading & Data Validation** | Python / pandas / openpyxl | Strict missing-value handling, no imputation |
| **Arithmetic & Feature Metrics** | Python pure functions | Exact reproducibility (baseline, decline %, annual value) |
| **Risk Causes, Labels & Watch Tier** | Python rule engine | Auditable thresholds & row evidence |
| **Ranking & 15-Slot Allocation** | Python deterministic sorting | Capacity enforcement and tie-breaks |
| **Obvious Note Classification** | Python Regex Patterns | Zero latency, no hallucination |
| **Ambiguous Notes (`UNKNOWN`)** | Selective LLM + Verification | Language nuances where rules are uncertain; **requires CSM confirmation** |
| **Top-15 Outreach Drafting** | Selective LLM / Fallback | Contextual, professional tone |
| **Draft Validation** | Python | Enforces sentence limits, merchant facts, and locked guardrails |
| **Sending Outreach** | Deliberately Not Built | **No message is ever sent automatically** |

---

## 📊 Key Findings on the Data Pack

- **Total Merchants Analyzed:** 100
- **Flagged Merchants (At-Risk Portfolio):** 24 (12 High, 12 Medium)
- **Unflagged Merchants:** 76 (43 No Risk Signal, 19 Low-Volume Stable, 8 Seasonal, 6 Growth, 0 Watch)
- **15-Slot Allocation (`label_first` Default):**
  - High-Risk Merchants Contacted: **12 / 12 (100%)**
  - Medium-Risk Merchants Contacted: **3 / 12**
  - Annual Value at Stake: **₹ 73.98 Lakh** (82.5% of flagged value)
- **Why `label_first` over `value_first`?**
  - Pure `value_first` leaves **7 of 12 High-risk merchants uncontacted** (including merchants with severe >8pt success rate drops like C2001, C2015, C2034) merely because their rupee volume is smaller. `label_first` prioritizes genuine operational and commercial severity.

---

## 🔒 Locked Outreach Guardrails
Every draft is fact-checked by a deterministic Python validator:
1. **Sentence count:** Exactly 3 to 5 sentences.
2. **Merchant facts only:** Every number in the draft must exist in the merchant's row or calculations.
3. **Prohibited terms:** Zero mention of "churn", "at risk", "model", "score", "rank", "discounts", "waivers", or "guarantees".
4. **Competitor & Note protection:** Never quote account notes or competitor names.
5. **No auto-send:** A human CSM must review and approve every draft.

---

## 📂 Project Structure
```
├── app.py                      # Streamlit 3-screen interactive application
├── config.yaml                 # Central configuration matching case assumptions
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── Buildathon_Student_Data_Pack.xlsx  # Provided competition dataset
├── src/
│   ├── loader.py               # Workbook validation & missing value handling
│   ├── features.py             # Deterministic feature engineering (TPV, spread)
│   ├── note_tagger.py          # Deterministic regex tagger with resolution logic
│   ├── scoring.py              # Cause grading (0-3), labels, Watch, playbooks
│   ├── ranking.py              # Renewal urgency, 15-slot allocation, overall rank
│   ├── value_scenario.py       # Financial scenarios, driver aggregation, static fixes
│   ├── validator.py            # Outreach draft compliance & numeric fact checker
│   ├── llm.py                  # Selective LLM integration & fallback templates
│   ├── orchestrator.py         # Lightweight agent orchestrator
│   └── exporter.py             # Excel & CSV audit export generator
├── tests/
│   └── test_engine.py          # 13 comprehensive unit, golden, & invariant tests
├── scripts/
│   └── generate_facts.py       # Deterministic facts generator
└── docs/
    ├── DECISIONS.md            # Architecture and implementation decisions record
    └── submission_facts.md     # Auto-generated portfolio facts from latest run
```
