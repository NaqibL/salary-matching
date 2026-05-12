"""Gemini Flash Lite implementation of the LLMJobCleaner Protocol.

Calls the OpenRouter API (OpenAI-compatible) to:
  1. Extract structured fields from the job description (min years experience,
     canonical skills, inferred seniority).
  2. Rewrite the description into query-aligned prose that mirrors how a
     candidate would phrase a search query, closing the embedding gap between
     job documents and candidate queries.

The two tasks are handled in one LLM call with a structured output format
that is parsed into an LLMCleanResult.  On any failure the original
description is returned with all extracted fields as None.

Usage
-----
Register at app startup (e.g. in server.py lifespan):

    from mcf.lib.embeddings.llm_cleaner import make_gemini_cleaner_from_env
    from mcf.lib.embeddings.job_description_extractor import register_llm_cleaner

    cleaner = make_gemini_cleaner_from_env()
    if cleaner:
        register_llm_cleaner(cleaner)

Environment variables
---------------------
OPENROUTER_API_KEY          Required. Your OpenRouter API key (sk-or-v1-...).
OPENROUTER_MODEL            Optional. Model slug (default: google/gemini-2.5-flash-lite-preview-06-17).
JOB_EXTRACTOR_LLM_ENABLED   Must be "1" for the extractor to call the cleaner.
"""

from __future__ import annotations

import json
import os
import re

import httpx

from mcf.lib.embeddings.job_description_extractor import LLMCleanResult, _LLM_THRESHOLD

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemini-2.5-flash-lite-preview-06-17"

_SYSTEM_PROMPT = """\
You process job descriptions for a job-matching search index. Given a job posting, \
you must output EXACTLY two sections separated by the markers below — nothing else.

===FIELDS===
Output a single JSON object on one line with these keys:
- "min_years_experience": integer (minimum years required) or null if not stated
- "canonical_skills": array of canonical skill/tool names (e.g. "Python", "React", \
"PostgreSQL", "AWS") or null if none found. Normalise casing (e.g. "Javascript" → \
"JavaScript", "Postgresql" → "PostgreSQL"). Max 15 skills.
- "inferred_seniority": one of "Entry", "Junior", "Mid", "Senior", "Lead", "Manager", \
"Director" or null if unclear

===CLEANED===
Rewrite the job description in plain, factual language that mirrors how a candidate \
would describe what they are looking for. Rules:
1. Write in third person (e.g. "Role requiring...", "Candidate must have...").
2. ONLY include: role responsibilities, required skills, experience requirements, \
education requirements, and seniority level.
3. OMIT entirely: company introductions, culture/values, benefits/perks, EEO notices, \
application instructions, and marketing language.
4. Be concise — aim for 100–250 words.
5. Do not invent any detail not present in the original posting.\
"""

_USER_TEMPLATE = """\
Job Title: {title}

--- BEGIN JOB DESCRIPTION ---
{description}
--- END JOB DESCRIPTION ---\
"""

_FIELDS_MARKER = "===FIELDS==="
_CLEANED_MARKER = "===CLEANED==="

# Fallback regex for extracting JSON from a response that doesn't follow the format exactly
_JSON_RE = re.compile(r"\{[^{}]+\}", re.DOTALL)


def _parse_response(raw: str, original_description: str) -> LLMCleanResult:
    """Parse the two-section LLM output into an LLMCleanResult.

    Tolerant of minor formatting deviations — uses marker positions rather
    than strict line counting.  Falls back gracefully on any parse failure.
    """
    fields_pos = raw.find(_FIELDS_MARKER)
    cleaned_pos = raw.find(_CLEANED_MARKER)

    # --- Extract cleaned text ---
    if cleaned_pos != -1:
        cleaned_text = raw[cleaned_pos + len(_CLEANED_MARKER):].strip()
    else:
        # No CLEANED marker — use the whole response as cleaned text
        cleaned_text = raw.strip()
    if not cleaned_text:
        cleaned_text = original_description

    # --- Extract structured fields ---
    min_years: int | None = None
    canonical_skills: list[str] | None = None
    inferred_seniority: str | None = None

    if fields_pos != -1:
        json_section_end = cleaned_pos if cleaned_pos > fields_pos else len(raw)
        json_block = raw[fields_pos + len(_FIELDS_MARKER):json_section_end].strip()
        try:
            parsed = json.loads(json_block)
        except json.JSONDecodeError:
            # Try to find any JSON object in the section
            m = _JSON_RE.search(json_block)
            try:
                parsed = json.loads(m.group()) if m else {}
            except (json.JSONDecodeError, AttributeError):
                parsed = {}

        raw_years = parsed.get("min_years_experience")
        if isinstance(raw_years, int) and raw_years >= 0:
            min_years = raw_years
        elif isinstance(raw_years, str) and raw_years.isdigit():
            min_years = int(raw_years)

        raw_skills = parsed.get("canonical_skills")
        if isinstance(raw_skills, list) and raw_skills:
            canonical_skills = [str(s).strip() for s in raw_skills if str(s).strip()][:15] or None

        raw_seniority = parsed.get("inferred_seniority")
        valid_seniorities = {"Entry", "Junior", "Mid", "Senior", "Lead", "Manager", "Director"}
        if isinstance(raw_seniority, str) and raw_seniority.strip() in valid_seniorities:
            inferred_seniority = raw_seniority.strip()

    return LLMCleanResult(
        cleaned_text=cleaned_text,
        min_years_experience=min_years,
        canonical_skills=canonical_skills,
        inferred_seniority=inferred_seniority,
    )


class GeminiFlashCleaner:
    """LLMJobCleaner implementation using Gemini Flash Lite via OpenRouter."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout: float = 45.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def should_clean(self, description: str) -> bool:
        return True

    def clean(self, description: str, title: str | None) -> LLMCleanResult:
        """Call the LLM and return a structured LLMCleanResult.

        Falls back to the original description (with all fields None) on any
        error so the pipeline never stalls.
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
            "max_tokens": 1200,
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
            raw: str = data["choices"][0]["message"]["content"]
            return _parse_response(raw, description)
        except Exception as exc:
            print(f"Warning: LLM cleaning failed ({exc}), using original.")
            self.last_input_tokens = 0
            self.last_output_tokens = 0
            return LLMCleanResult(cleaned_text=description)


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def make_gemini_cleaner_from_env() -> GeminiFlashCleaner | None:
    """Build a GeminiFlashCleaner from environment variables.

    Returns None if OPENROUTER_API_KEY is not set.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    return GeminiFlashCleaner(api_key=api_key, model=model)


# Keep old name as an alias so existing server.py startup code doesn't break
make_openrouter_cleaner_from_env = make_gemini_cleaner_from_env
