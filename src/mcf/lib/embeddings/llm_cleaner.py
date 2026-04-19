"""OpenRouter implementation of the LLMJobCleaner Protocol.

Calls OpenRouter's OpenAI-compatible chat completions API to extractively
clean job descriptions before embedding.  Only sentences and bullet points
that exist verbatim in the original are kept — no paraphrasing.

Usage
-----
Register at app startup (e.g. in server.py lifespan):

    from mcf.lib.embeddings.llm_cleaner import make_openrouter_cleaner_from_env
    from mcf.lib.embeddings.job_description_extractor import register_llm_cleaner

    cleaner = make_openrouter_cleaner_from_env()
    if cleaner:
        register_llm_cleaner(cleaner)

Environment variables
---------------------
OPENROUTER_API_KEY      Required. Your OpenRouter API key (sk-or-v1-...).
OPENROUTER_MODEL        Optional. Model slug (default: google/gemma-3-27b-it:free).
JOB_EXTRACTOR_LLM_ENABLED   Must be "1" for the extractor to call the cleaner.
JOB_EXTRACTOR_LLM_THRESHOLD Optional. Word count above which LLM is invoked (default 800).
"""

from __future__ import annotations

import os
import time

import httpx

from mcf.lib.embeddings.job_description_extractor import _LLM_THRESHOLD

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemma-3-27b-it:free"

_SYSTEM_PROMPT = """\
You are a precise text extractor for a job-search index.
Your only job is to copy the most relevant parts of a job posting — \
word for word — and discard noise.

Rules (follow exactly):
1. COPY exact sentences and bullet points from the original text.
2. NEVER paraphrase, summarise, rewrite, or add any words not in the original.
3. REMOVE the following sections entirely:
   - Company / team introductions ("About Us", "Who We Are", "Our Story")
   - Employer branding and culture ("Why Join Us", "Our Values", "Dynamic team")
   - Benefits and perks (annual leave, medical, dental, flexible hours, bonuses)
   - EEO / PDPA / legal notices ("Equal Opportunity Employer", "only shortlisted")
   - Application instructions ("How to Apply", "Send your CV", "Click Apply")
4. KEEP the following content:
   - Job responsibilities and duties
   - Required qualifications, skills, and competencies
   - Years of experience requirements
   - Educational requirements (degrees, diplomas, certifications)
   - Technical skills and tools required
5. Output only the extracted text. No headings, no preamble, no commentary.\
"""

_USER_TEMPLATE = """\
Job Title: {title}

--- BEGIN JOB DESCRIPTION ---
{description}
--- END JOB DESCRIPTION ---

Extract the high-signal content following the rules above.\
"""


class OpenRouterJobCleaner:
    """LLMJobCleaner implementation backed by OpenRouter."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        # Populated after each clean() call — read by the test script for cost tracking
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    # ------------------------------------------------------------------
    # LLMJobCleaner Protocol
    # ------------------------------------------------------------------

    def should_clean(self, description: str) -> bool:
        """Always clean — LLM quality justifies calling it on every description."""
        return True

    def clean(self, description: str, title: str | None) -> str:
        """Call OpenRouter and return extractively cleaned description.

        Falls back to the original description on any error so the pipeline
        never stalls due to a network issue or API outage.
        """
        user_msg = _USER_TEMPLATE.format(
            title=title or "Unknown",
            description=description,
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mcf-job-matcher",
        }
        try:
            resp = httpx.post(
                _OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            self.last_input_tokens = usage.get("prompt_tokens", 0)
            self.last_output_tokens = usage.get("completion_tokens", 0)
            content: str = data["choices"][0]["message"]["content"].strip()
            return content if content else description
        except Exception as exc:
            print(f"Warning: OpenRouter LLM cleaning failed ({exc}), using original.")
            self.last_input_tokens = 0
            self.last_output_tokens = 0
            return description


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def make_openrouter_cleaner_from_env() -> OpenRouterJobCleaner | None:
    """Build an OpenRouterJobCleaner from environment variables.

    Returns None if OPENROUTER_API_KEY is not set, so callers can safely
    skip registration without error.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    return OpenRouterJobCleaner(api_key=api_key, model=model)
