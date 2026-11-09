"""
Selective LLM integration and deterministic fallback module.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import json
import re
import requests
from src.validator import validate_draft
from src.note_tagger import ALLOWED_TAGS


class LLMService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        self.model_name = os.getenv("MODEL_NAME", "").strip()
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or os.getenv("CLAUDE_API_KEY", "").strip()

        # Session cache: {cache_key: response}
        self.note_cache: Dict[str, Dict[str, Any]] = {}
        self.draft_cache: Dict[str, str] = {}

    def is_available(self) -> bool:
        """Returns True if a valid API key and provider/model are configured."""
        if self.anthropic_key:
            return True
        if self.gemini_key:
            return True
        if self.openai_key:
            return True
        return False

    def suggest_note_tag(self, note: Any) -> Dict[str, Any]:
        """
        Sends an ambiguous note to the LLM for a structured tag suggestion.
        Returns dict with: tag, explanation, evidence_phrase, ambiguity_indicator.
        """
        if note is None or (isinstance(note, float) and (note != note or str(note) == "nan")) or str(note).strip() == "":
            return {
                "tag": "BLANK",
                "explanation": "Note is empty.",
                "evidence_phrase": "",
                "ambiguity_indicator": False,
            }

        note_clean = str(note).strip()
        if note_clean.lower() == "nan":
            return {
                "tag": "BLANK",
                "explanation": "Note is empty.",
                "evidence_phrase": "",
                "ambiguity_indicator": False,
            }
        if note_clean in self.note_cache:
            return self.note_cache[note_clean]

        if not self.is_available():
            res = {
                "tag": "UNKNOWN",
                "explanation": "No LLM API key configured.",
                "evidence_phrase": "",
                "ambiguity_indicator": True,
            }
            self.note_cache[note_clean] = res
            return res

        prompt = f"""You are an assistant categorising an account manager's notes for Razorpay merchants.
Allowed tags are exactly one of: {', '.join([t for t in ALLOWED_TAGS if t not in ['UNKNOWN', 'BLANK']])} or UNKNOWN.

Rules:
1. Do NOT infer facts not present in the note.
2. If the note is genuinely ambiguous or does not fit any category, return UNKNOWN.
3. The evidence_phrase MUST be an exact verbatim substring from the note.

Note:
\"\"\"{note_clean}\"\"\"

Respond strictly in JSON format with these exact keys:
{{
  "tag": "ONE_ALLOWED_TAG",
  "explanation": "Brief explanation",
  "evidence_phrase": "exact verbatim excerpt from note",
  "ambiguity_indicator": true/false
}}
"""

        try:
            raw_response = self._call_llm(prompt, temperature=0.0)
            parsed = self._extract_json(raw_response)
            tag = parsed.get("tag", "UNKNOWN").strip().upper()
            evidence = parsed.get("evidence_phrase", "").strip()
            explanation = parsed.get("explanation", "").strip()
            ambiguity = bool(parsed.get("ambiguity_indicator", False))

            # Validation: tag must be in allowed tags
            if tag not in ALLOWED_TAGS:
                tag = "UNKNOWN"

            # Validation: evidence phrase must appear in original note (case-insensitive)
            if evidence and evidence.lower() not in note_clean.lower():
                tag = "UNKNOWN"
                explanation = "AI evidence phrase was not found in original note text."

            result = {
                "tag": tag,
                "explanation": explanation,
                "evidence_phrase": evidence,
                "ambiguity_indicator": ambiguity,
            }
        except Exception as e:
            result = {
                "tag": "UNKNOWN",
                "explanation": f"LLM error: {str(e)}",
                "evidence_phrase": "",
                "ambiguity_indicator": True,
            }

        self.note_cache[note_clean] = result
        return result

    def generate_outreach_draft(
        self,
        merchant: Dict[str, Any],
        max_revision: bool = True,
    ) -> Tuple[str, str, List[str], str]:
        """
        Generates outreach draft for a top 15 Contact now merchant.
        Returns (draft_text, status, validation_errors, provenance).
        """
        m_id = str(merchant.get("merchant_id", ""))
        cache_key = f"{m_id}_{merchant.get('primary_playbook')}"
        if cache_key in self.draft_cache:
            text = self.draft_cache[cache_key]
            is_valid, errors = validate_draft(text, merchant)
            status = "Draft" if is_valid else "Needs manual edit"
            return text, status, errors, "Cached AI draft"

        if not self.is_available():
            fallback_text = self._build_deterministic_fallback(merchant)
            is_valid, errors = validate_draft(fallback_text, merchant)
            status = "Draft" if is_valid else "Needs manual edit"
            return fallback_text, status, errors, "Deterministic Fallback"

        # Prepare prompt
        prompt = self._build_outreach_prompt(merchant)
        try:
            draft_text = self._call_llm(prompt, temperature=0.2).strip()
            draft_text = self._clean_llm_draft(draft_text)
            is_valid, errors = validate_draft(draft_text, merchant)

            # Revision request if failed
            if not is_valid and max_revision:
                rev_prompt = f"""Your previous draft failed compliance validation for the following reasons:
{chr(10).join(f"- {e}" for e in errors)}

Merchant Information:
{self._format_merchant_context(merchant)}

Please rewrite the draft strictly adhering to these rules:
- Must be between 3 and 5 sentences.
- Must be explicitly addressed to {merchant.get('business_name')}.
- Do NOT make up any numbers or commitments.
- Propose a 15-minute call or review without promising discounts, waivers, or guaranteed outcomes.
"""
                rev_text = self._call_llm(rev_prompt, temperature=0.1).strip()
                rev_text = self._clean_llm_draft(rev_text)
                is_valid_rev, errors_rev = validate_draft(rev_text, merchant)
                if is_valid_rev:
                    self.draft_cache[cache_key] = rev_text
                    return rev_text, "Draft", [], "AI Draft (revised)"
                else:
                    self.draft_cache[cache_key] = rev_text
                    return rev_text, "Needs manual edit", errors_rev, "AI Draft (validation failed)"

            status = "Draft" if is_valid else "Needs manual edit"
            self.draft_cache[cache_key] = draft_text
            return draft_text, status, errors, "AI Draft"

        except Exception as e:
            fallback_text = self._build_deterministic_fallback(merchant)
            is_valid, errors = validate_draft(fallback_text, merchant)
            status = "Draft" if is_valid else "Needs manual edit"
            return fallback_text, status, errors, f"Deterministic Fallback (LLM error: {str(e)})"

    def _build_outreach_prompt(self, merchant: Dict[str, Any]) -> str:
        ctx = self._format_merchant_context(merchant)
        pb = merchant.get("primary_playbook")
        segment = merchant.get("segment", "Mid")

        guidance = {
            "PB-1": "Reference recent success rate movements and offer a joint review call with the payments team to review performance by method and bank.",
            "PB-2": "Reference unresolved support tickets and offer to take direct ownership as a single point of contact.",
            "PB-3": "Reference upcoming contract renewal timing and offer to walk through volume tiers, rate card, and renewal terms before renewal.",
            "PB-4": "Reference dashboard usage and products in use, and offer a short walkthrough of relevant products and reports.",
        }.get(pb, "Propose a check-in call to review account health.")

        tone_guidance = {
            "Enterprise": "Propose an account-level review with senior stakeholders on both sides.",
            "Mid": "Standard call request with an offer to partner closely.",
            "Small": "Shorter message with one concrete ask; offer a 15-minute walkthrough, not a workshop.",
        }.get(segment, "Standard professional check-in.")

        return f"""You are drafting a concise outreach message from a Razorpay CSM to a merchant.

Merchant Context:
{ctx}

Primary Objective ({pb}):
{guidance}

Segment Tone ({segment}):
{tone_guidance}

Guardrails (Strictly Enforced):
- Must be exactly 3 to 5 sentences.
- Must be addressed to '{merchant.get('business_name')}'.
- Only use facts supplied above. Never invent numbers, dates, contacts, or competitor names.
- Do NOT offer discounts, price cuts, fee waivers, special rates, or guaranteed outcomes.
- Never use words: 'churn', 'at risk', 'our model', 'score', 'rank', 'label', 'deadline', 'promise'.
- Never quote internal account manager notes.
- Do NOT invent a CSM name or specific meeting time. Ask for a brief 15-minute conversation.

Draft the message now:
"""

    def _format_merchant_context(self, merchant: Dict[str, Any]) -> str:
        return f"""- Business Name: {merchant.get('business_name')}
- Segment: {merchant.get('segment')}
- City: {merchant.get('city')}
- Primary Playbook: {merchant.get('primary_playbook')}
- Secondary Playbooks: {', '.join(merchant.get('secondary_playbooks', []))}
- Key Reason: {merchant.get('reason')}
- Success Rate (M1-M3): {merchant.get('success_rate_m1_m3_pct')}%
- Success Rate (M4-M6): {merchant.get('success_rate_m4_m6_pct')}%
- Unresolved Tickets: {merchant.get('unresolved_tickets')}
- Days to Renewal: {merchant.get('days_to_contract_renewal')}
- Products Used: {merchant.get('products_used')}
- Logins Last 30d: {merchant.get('logins_last_30d')}
"""

    def _build_deterministic_fallback(self, merchant: Dict[str, Any]) -> str:
        """
        Creates a high-quality deterministic fallback draft conforming to all guardrails.
        """
        name = merchant.get("business_name") or "Merchant Partner"
        pb = merchant.get("primary_playbook", "PB-1")
        segment = merchant.get("segment", "Mid")
        sr1 = merchant.get("success_rate_m1_m3_pct")
        sr2 = merchant.get("success_rate_m4_m6_pct")
        unresolved = merchant.get("unresolved_tickets")
        renewal_days = merchant.get("days_to_contract_renewal")
        products = merchant.get("products_used")

        # Sentence 1: Greeting & context
        if pb == "PB-1" and sr1 is not None and sr2 is not None:
            s1 = f"Dear {name} team, we have been closely monitoring payment trends and noticed success rates moved from {sr1:.1f}% to {sr2:.1f}% over recent months."
            s2 = "Our payments operations team would like to review performance across specific payment methods and banks to optimize transaction success."
            s3 = "We would appreciate a brief 15-minute call this week to share our findings and discuss optimization steps."
        elif pb == "PB-2" and unresolved is not None:
            s1 = f"Dear {name} team, we are reaching out regarding the {int(unresolved)} open support tickets on your account."
            s2 = "We want to ensure these operational concerns are prioritized and resolved promptly by serving as your dedicated escalation point."
            s3 = "Could we schedule a quick 15-minute review call this week to walk through each pending ticket and align on resolution steps?"
        elif pb == "PB-3" and renewal_days is not None:
            s1 = f"Dear {name} team, with your contract renewal coming up in {int(renewal_days)} days, we want to proactively review your account terms."
            s2 = "We would welcome the opportunity to walk through your transaction volume tiers and discuss appropriate commercial terms ahead of the renewal window."
            s3 = "Please let us know if you have 15 minutes available this week for a collaborative account review."
        elif pb == "PB-4" and products is not None:
            s1 = f"Dear {name} team, we noticed your team is currently active on {int(products)} Razorpay products and wanted to check in on your platform experience."
            s2 = "We would be delighted to host a short walkthrough of feature updates, analytics reports, and tools designed to streamline your daily workflows."
            s3 = "Could we set up a 15-minute check-in call this week to ensure your team has all the resources needed?"
        else:
            s1 = f"Dear {name} team, we are checking in to review your current payment operations on Razorpay."
            s2 = "Our team is focused on ensuring seamless transactions and resolving any operational questions you may have."
            s3 = "Please let us know if a brief 15-minute check-in call this week would suit your schedule."

        # Segment customization: 4th sentence if Enterprise
        if segment == "Enterprise":
            s4 = "We look forward to partnering with your senior leadership team to support your ongoing business objectives."
            return f"{s1} {s2} {s3} {s4}"

        return f"{s1} {s2} {s3}"

    def _call_llm(self, prompt: str, temperature: float = 0.0) -> str:
        """Invokes Anthropic Claude, Gemini, or OpenAI API based on environment variables."""
        if self.anthropic_key or self.provider in ["anthropic", "claude"]:
            key = self.anthropic_key
            model = self.model_name or "claude-sonnet-4-6"
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 1024,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            # If the user-specified model returned 404, fallback to an active Sonnet or Haiku model
            if resp.status_code == 404:
                for fallback_m in ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]:
                    payload["model"] = fallback_m
                    resp = requests.post(url, headers=headers, json=payload, timeout=25)
                    if resp.status_code == 200:
                        break
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

        elif self.gemini_key:
            model = self.model_name or "gemini-1.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
            }
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        elif self.openai_key:
            model = self.model_name or "gpt-4o-mini"
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.openai_key}"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        raise ValueError("No LLM API key available.")

    def _clean_llm_draft(self, text: str) -> str:
        # Remove markdown quotes, backticks, or intro headers
        text = re.sub(r"^```[\w]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.replace('"', '').strip()
        return text

    def _extract_json(self, text: str) -> Dict[str, Any]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text)
