# Razorpay Early-Warning Submission Facts

*Generated directly from deterministic execution against `Buildathon_Student_Data_Pack.xlsx`.*
*Workbook SHA-256:* `9dd4af798e75d4527796a6011bcfba24517158c6e598c60ac5dddba6ff08201b`

---

## 1. Portfolio Breakdown & Classification

- **Total Merchants Analyzed:** 100
- **Flagged Merchants (At-Risk Portfolio):** 24
  - **High Risk:** 12 merchants
  - **Medium Risk:** 12 merchants
- **Unflagged Merchants (Low Risk):** 76
  - **No Risk Signal (PB-6):** 43
  - **Low-volume Stable (PB-6):** 19
  - **Seasonal (PB-6):** 8 (C2012, C2023, C2048, C2054, C2065, C2066, C2067, C2094)
  - **Growth (PB-5):** 6 (C2003, C2083, C2072, C2043, C2016, C2078)
  - **Watch Tier:** 0

---

## 2. Selection & Ranking Comparison (15 Slots)

| Metric | Label-First (Default) | Value-First (Alternative) |
|---|---|---|
| **High-Risk Merchants Contacted** | 12 / 12 | 5 / 12 |
| **Medium-Risk Merchants Contacted** | 3 / 12 | 10 / 12 |
| **Annual Value at Stake** | Rs 7,398,000 (73.98L) | Rs 8,407,200 (84.07L) |
| **Coverage of Flagged Value (Rs 8,972,400)** | 82.5% | 93.7% |

### Top 15 Selected IDs:
- **`label_first`:** C2088, C2090, C2097, C2100, C2061, C2032, C2034, C2015, C2001, C2008, C2045, C2020, C2004, C2018, C2079
- **`value_first`:** C2004, C2088, C2018, C2090, C2079, C2097, C2027, C2062, C2100, C2093, C2061, C2084, C2022, C2036, C2092

### Portfolio Differences:
- **In `label_first` only (prioritising genuine operational severity):** C2001, C2008, C2015, C2020, C2032, C2034, C2045
  - *These include High-risk merchants with severe success rate drops (e.g. C2001, C2015, C2034) that are displaced in pure value ranking.*
- **In `value_first` only (prioritising gross rupee coverage):** C2022, C2027, C2036, C2062, C2084, C2092, C2093

---

## 3. Financial Scenario Analysis (Assumed Likelihood 0.75, Save Rate 0.25)

- **Total Outreach Cost:** Rs 22,500 (15 merchants × Rs 1,500 assumed outreach cost)
- **Net Value (`label_first`):** Rs 1,364,625
- **Net Value (`value_first`):** Rs 1,553,850
- **Break-Even Save Rate:**
  - `label_first`: 0.406%
  - `value_first`: 0.357%

*Disclaimer: Scenario calculations are based on assumed parameters, not forecast models.*

---

## 4. Key Root Cause Drivers & Suggested Process Fixes

| Playbook | Description | Flagged Count | Annual Value at Stake | In Top 15 |
|---|---|---|---|---|
| **PB-1** | Performance (PB-1) | 7 | Rs 2,493,600 | 7 |
| **PB-2** | Service (PB-2) | 6 | Rs 1,558,800 | 1 |
| **PB-3** | Commercial (PB-3) | 6 | Rs 3,861,600 | 2 |
| **PB-4** | Disengagement (PB-4) | 5 | Rs 1,058,400 | 5 |

**Largest Risk Driver:** Commercial (PB-3) (Rs 3,861,600 at stake).

**Recommended Operational Process Fix:**
> Add a structured 'competitor or pricing request' field in the CRM and start a commercial review 90 days before renewal. Commercial risk is visible through notes, so it can be missed when notes are blank.

---

## 5. Robustness & Stability Checks

1. **Notes Removed Test (Stress Test):**
   - Blanking 100% of account notes results in exactly **18 of 24** merchants remaining flagged.
   - The 6 lost merchants are exactly the commercial group: `C2004, C2018, C2022, C2036, C2040, C2092`.
   - Zero decoys are falsely flagged.
2. **Deterministic Reproducibility:**
   - 100% identical outputs for any identical workbook, config parameters, and confirmed note tags.
