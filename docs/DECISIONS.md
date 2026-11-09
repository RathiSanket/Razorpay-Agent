# Implementation Decisions & Record

## Record of Architecture and Design Decisions

1. **Lightweight Python Orchestration:** Ordinary Python functions and dataclasses/dictionaries manage the workflow state. LangGraph or multi-agent abstractions are intentionally omitted to avoid unnecessary complexity and latency.
2. **Deterministic-First Core:** All financial metrics, derived features, risk signals, cause levels, non-flag classifications, ranking, and scenario numbers are computed purely in Python.
3. **Selective LLM Integration:** LLM calls are limited exclusively to:
   - Suggesting a tag for account manager notes classified as `UNKNOWN` by the deterministic pattern matcher (human confirmation required before scoring).
   - Drafting personalized 3-5 sentence outreach for the selected 15 `Contact now` merchants.
   - At most 1 revision if the outreach draft fails Python validation.
4. **Deterministic Fallbacks:** When `LLM_PROVIDER` or API key is absent or when an LLM call fails/times out, the system seamlessly falls back to deterministic playbook templates and leaves unknown notes as `UNKNOWN` (with manual tagging available in the UI).
5. **Exact Missing Value Handling:** Unknown inputs strictly propagate as `None`. Division by zero or missing TPV months yield unknown features without silent pandas imputation.
