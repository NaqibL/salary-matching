"""OpenRouter LLM cleaner for resume text.

Converts raw extracted resume text into a compact structured format that
mirrors the job text schema, closing the query-document gap for BGE retrieval.

Environment variables
---------------------
OPENROUTER_API_KEY   Required. Your OpenRouter API key (sk-or-v1-...).
OPENROUTER_MODEL     Optional. Model slug (default: google/gemma-3-27b-it:free).
RESUME_LLM_ENABLED   Must be "1" to activate (default: 0 — heuristic only).
"""

from __future__ import annotations

import os

import httpx

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemma-3-27b-it:free"

_SYSTEM_PROMPT = """\
You are a resume parser for a job-matching search index.
Convert the raw resume text into a compact structured block used for semantic search.

Output format (use only the labels that have content):
Skills: <comma-separated list, technical skills first>
Experience Level: <seniority level>, <total years> years <domain>
Recent Role: <most recent job title only, no company name>
Summary: <2-3 factual sentences on key responsibilities and achievements>
Education: <highest degree and field only, no institution>

Rules (follow exactly):
1. Skills: list every technical skill, tool, language, and framework mentioned. Soft skills last.
2. Experience Level: infer seniority (Junior / Mid / Senior / Lead / Principal / Manager / Director / C-level) from titles and years. Count total years of work experience from dates.
3. Recent Role: use the most recent job title verbatim. Omit company name, location, and dates.
4. Summary: write 2-3 sentences that describe what the person has done and what they are good at. Base this strictly on what the resume states — do not invent or embellish.
5. Education: state only the highest degree and its field (e.g. "B.Sc. Computer Science", "MBA Finance"). No institution names.
6. Omit any label for which there is no signal in the resume.
7. Strip all personal information: name, email, phone, address, LinkedIn, GitHub URLs.
8. Output ONLY the structured block. No preamble, no commentary, no extra blank lines.\
"""

_USER_TEMPLATE = """\
--- BEGIN RESUME ---
{resume_text}
--- END RESUME ---

Extract the structured block following the rules above.\
"""


class OpenRouterResumeCleaner:
    """Converts raw resume text into a structured format optimised for BGE embedding."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout

    def clean(self, resume_text: str) -> str | None:
        """Call OpenRouter and return structured resume text, or None on failure."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_TEMPLATE.format(resume_text=resume_text)},
            ],
            "temperature": 0.0,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mcf-job-matcher",
        }
        resp = httpx.post(
            _OPENROUTER_URL,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        content: str = resp.json()["choices"][0]["message"]["content"].strip()
        return content or None


def make_resume_cleaner_from_env() -> OpenRouterResumeCleaner | None:
    """Build an OpenRouterResumeCleaner from environment variables.

    Returns None if OPENROUTER_API_KEY is not set or RESUME_LLM_ENABLED != "1".
    """
    if os.getenv("RESUME_LLM_ENABLED", "0") != "1":
        return None
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    return OpenRouterResumeCleaner(api_key=api_key, model=model)
