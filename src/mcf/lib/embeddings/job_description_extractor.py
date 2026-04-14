"""High-signal job description extraction for embedding.

Replaces the naive "first 300 words" truncation with a salience-scored block
extraction pipeline:

  1. Split the description into meaningful blocks (paragraphs or sentences).
  2. Score each block by positive signals (requirements, skills, tools, years of
     experience) and negative signals (boilerplate, marketing, benefits, EEO).
  3. Greedily select the highest-scoring blocks that fit within a token budget.
  4. Return selected blocks in their original order (not score order) to preserve
     logical flow for the embedder.

All scoring weights and patterns are module-level constants so they can be
tuned without touching the logic.

Phase 2 LLM path
-----------------
An optional LLM-assisted extractive cleaner can be registered at startup via
``register_llm_cleaner()``.  It is disabled by default (requires the env var
``JOB_EXTRACTOR_LLM_ENABLED=1``) and is only ever called at ingestion /
re-embed time, never at query/retrieval time.  See ``LLMJobCleaner`` for the
interface contract and the module-level docstring for integration notes.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Protocol

# ---------------------------------------------------------------------------
# Scoring weights  (all tunable without touching logic below)
# ---------------------------------------------------------------------------

# Positive: awarded per matching signal found in a block
_W_SECTION_HEADER = 3.0  # block starts with a high-signal section header
_W_BULLET_LIST = 1.5     # block contains bullet-point items
_W_TECH_TOOL = 2.0       # contains a tech tool / framework / language name
_W_YEARS_EXP = 2.5       # "3+ years experience", "minimum 2 years"
_W_DEGREE_CERT = 2.0     # "bachelor's", "diploma", "certification"
_W_TITLE_OVERLAP = 1.5   # significant word overlap with job title
_W_SENIORITY = 1.0       # "senior", "lead", "principal", "staff"
_W_FACTUAL_CONCISE = 0.5 # short, factual block (likely a requirement bullet)

# Negative: deducted per matching signal
_W_BOILERPLATE = -10.0   # company-intro / EEO / benefits / application-process
_W_MARKETING_PROSE = -2.0  # high we/our density → marketing paragraph
_W_GENERIC_FILLER = -1.0   # very long sentence with no signal words

# ---------------------------------------------------------------------------
# Positive patterns
# ---------------------------------------------------------------------------

# Section headers that introduce high-signal content.
_RE_SECTION_HEADER = re.compile(
    r"^("
    r"requirements?|qualifications?|responsibilities|what you.ll do"
    r"|you will|must[\s-]have|key skills?|technical skills?"
    r"|about the role|role overview|job scope|job requirements?"
    r"|skills? (required|needed)|experience required"
    r"|key responsibilities|main duties|what we.re looking for"
    r"|your profile|candidate requirements?"
    r")",
    re.IGNORECASE,
)

# Technology tools, languages, frameworks, platforms (extensible list).
_RE_TECH_TOOL = re.compile(
    r"\b("
    r"python|java\b|javascript|typescript|react|angular|vue|node\.?js"
    r"|django|flask|fastapi|spring|\.net|c\+\+|c#|golang|rust|scala|kotlin"
    r"|sql|mysql|postgresql|postgres|sqlite|mongodb|redis|elasticsearch"
    r"|aws|azure|gcp|google cloud|kubernetes|k8s|docker|terraform|ansible"
    r"|machine learning|deep learning|nlp|computer vision|data science"
    r"|pandas|numpy|scikit.learn|tensorflow|pytorch|spark|hadoop"
    r"|git|ci/cd|devops|agile|scrum|jira|confluence"
    r"|rest\s*api|graphql|microservices|api\b"
    r"|linux|unix|bash|powershell"
    r")",
    re.IGNORECASE,
)

# Years of experience patterns.
_RE_YEARS_EXP = re.compile(
    r"\d+\+?\s*(?:-\s*\d+\s*)?"  # "3+", "3-5"
    r"years?\s+(?:of\s+)?(?:relevant\s+)?(?:working\s+)?(?:experience|exp\b)",
    re.IGNORECASE,
)

# Degree / certification / licensing.
_RE_DEGREE_CERT = re.compile(
    r"\b(bachelor|master|phd|doctorate|diploma|degree|certified|certification"
    r"|professional\s+cert|license|licence|cpa|cfa|pmp|aws\s+certified"
    r"|gcse|a.level)\b",
    re.IGNORECASE,
)

# Seniority cues.
_RE_SENIORITY = re.compile(
    r"\b(senior|junior|lead\b|principal|staff\b|mid.level|entry.level"
    r"|associate|vp\b|director|manager|head\s+of)\b",
    re.IGNORECASE,
)

# Bullet-list indicators (line starts with a bullet/dash/number, or block has
# multiple such lines).
_RE_BULLET_LINE = re.compile(r"^[\-\*\u2022\u25aa\u2023\u25b8\d]+[\.\)]\s", re.MULTILINE)

# ---------------------------------------------------------------------------
# Negative / boilerplate patterns
# ---------------------------------------------------------------------------

# Company intro / employer branding headers.
_RE_BOILERPLATE_COMPANY = re.compile(
    r"\b(about\s+(us|the\s+company|our\s+company|the\s+team|the\s+role\s+of)"
    r"|who\s+we\s+are|our\s+story|company\s+overview|company\s+profile"
    r"|about\s+the\s+firm|about\s+our\s+client)\b",
    re.IGNORECASE,
)

# Marketing / culture / mission content.
_RE_BOILERPLATE_CULTURE = re.compile(
    r"\b(why\s+join\s+(us|our\s+team)?|what\s+we\s+offer|our\s+culture"
    r"|our\s+values?|work.life\s+balance|our\s+mission|our\s+vision"
    r"|be\s+part\s+of\s+(our|a)\s+(team|journey)|join\s+our\s+team"
    r"|fast.growing\s+(company|team|startup)|exciting\s+opportunity"
    r"|innovative\s+(company|team)|dynamic\s+(team|environment))\b",
    re.IGNORECASE,
)

# Benefits / perks / compensation sections.
_RE_BOILERPLATE_BENEFITS = re.compile(
    r"\b(benefits?\s+(package|include|offered)?|perks?\b"
    r"|annual\s+leave|medical\s+(coverage|insurance|benefits?)"
    r"|dental\s+(coverage|benefits?)|health\s+insurance"
    r"|flexible\s+(working|hours|arrangement)"
    r"|staff\s+(discount|welfare|activities)"
    r"|competitive\s+salary|attractive\s+(remuneration|package)"
    r"|variable\s+bonus|performance\s+bonus)\b",
    re.IGNORECASE,
)

# EEO / legal / privacy notices.
_RE_BOILERPLATE_LEGAL = re.compile(
    r"\b(equal\s+opportunity\s+employer|pdpa|personal\s+data\s+protection"
    r"|privacy\s+notice|all\s+applications?\s+will\s+be"
    r"|only\s+shortlisted\s+candidates?"
    r"|we\s+regret\s+(to\s+inform|that\s+only)"
    r"|treated\s+in\s+(strict\s+)?confidence"
    r"|by\s+(submitting|applying|sending)\b.{0,60}(resume|cv|application)"
    r"|do\s+not\s+hear\s+from\s+us)\b",
    re.IGNORECASE,
)

# How-to-apply / application process.
_RE_BOILERPLATE_APPLY = re.compile(
    r"\b(how\s+to\s+apply|to\s+apply\b|application\s+process"
    r"|send\s+your\s+(resume|cv)|click\s+(apply|here\s+to\s+apply)"
    r"|interested\s+candidates?\s+(may|please|are\s+invited)"
    r"|drop\s+your\s+(resume|cv))\b",
    re.IGNORECASE,
)

# High we/our density → marketing paragraph (pattern: multiple we/our/us in
# close proximity — indicative of company-branding prose).
_RE_WE_OUR = re.compile(r"\b(we|our|us)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# All boilerplate patterns combined (for quick full-block rejection)
# ---------------------------------------------------------------------------
_BOILERPLATE_PATTERNS: list[re.Pattern] = [
    _RE_BOILERPLATE_COMPANY,
    _RE_BOILERPLATE_CULTURE,
    _RE_BOILERPLATE_BENEFITS,
    _RE_BOILERPLATE_LEGAL,
    _RE_BOILERPLATE_APPLY,
]

# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

# Default maximum tokens for the description portion of the embedding text.
# The structured metadata fields (title, skills, seniority) consume ~100-130
# tokens, leaving the rest for description content within BGE's 512-token limit.
_DEFAULT_MAX_DESCRIPTION_TOKENS = 380

# Minimum word count below which we skip extraction and pass the text through
# unchanged.  Only truly short descriptions (single-sentence, stub content)
# should bypass extraction.  Set low so that even modest 60-word descriptions
# still get scored — many real postings pack boilerplate into that space.
_PASSTHROUGH_WORD_THRESHOLD = 40


def _heuristic_token_count(text: str) -> int:
    """Estimate token count using the 0.75 words/token heuristic.

    Used when the actual model tokenizer is not available.  Slightly
    over-estimates to ensure we stay safely within the model budget.
    """
    return len(text.split()) * 4 // 3


# ---------------------------------------------------------------------------
# Block splitting
# ---------------------------------------------------------------------------


def _split_into_blocks(text: str) -> list[str]:
    """Split a description into meaningful scoring units.

    Strategy:
      - If the text has blank-line separators (``\\n\\n``), split on those
        to get one block per *paragraph / section*.  This keeps each section
        header together with its content so the boilerplate detector can
        match the header and penalise the whole block.
      - If the text has single-newlines only (e.g. bullet clusters or
        descriptions stored before the structure-preserving clean fix),
        split on single ``\\n`` instead.
      - If there are no newlines at all (flat scraped text), fall back to
        sentence-level splitting on .  !  ? boundaries.

    Blocks shorter than 10 characters are discarded as stubs.
    """
    min_len = 10

    if "\n\n" in text:
        # Paragraph-level split: keeps section header + body together so the
        # header phrase triggers the correct boilerplate / signal score.
        raw = re.split(r"\n\n+", text)
        strategy = "structured"
    elif "\n" in text:
        # Line-level split for descriptions without blank-line separators.
        raw = re.split(r"\n+", text)
        strategy = "structured"
    else:
        # Sentence-level fallback for completely flat scraped text.
        raw = re.split(r"(?<=[.!?])\s+", text)
        strategy = "flat"

    blocks = [b.strip() for b in raw if b.strip() and len(b.strip()) >= min_len]
    return blocks, strategy  # type: ignore[return-value]  # tuple returned intentionally


# ---------------------------------------------------------------------------
# Salience scoring
# ---------------------------------------------------------------------------


def _score_block(block: str, title_words: frozenset[str]) -> float:
    """Return a salience score for one block.  Higher = more useful for embedding.

    Scoring is purely additive/subtractive from the matched patterns.  A block
    that hits multiple positive signals and no negatives will rank highest.
    """
    score = 0.0
    block_lower = block.lower()

    # --- Boilerplate check (hard penalty, dominates score) ---
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(block):
            score += _W_BOILERPLATE
            break  # one boilerplate match is enough

    # --- Positive signals ---

    # Section header (check the *start* of the block)
    first_line = block.split("\n")[0].strip()
    if _RE_SECTION_HEADER.match(first_line):
        score += _W_SECTION_HEADER

    # Bullet list: multiple lines starting with a bullet/dash/number
    bullet_matches = len(_RE_BULLET_LINE.findall(block))
    if bullet_matches >= 2:
        score += _W_BULLET_LIST
    elif bullet_matches == 1:
        score += _W_BULLET_LIST * 0.5

    # Technology / tool mentions
    tech_matches = len(_RE_TECH_TOOL.findall(block))
    if tech_matches >= 3:
        score += _W_TECH_TOOL * 1.5
    elif tech_matches >= 1:
        score += _W_TECH_TOOL

    # Years of experience
    if _RE_YEARS_EXP.search(block):
        score += _W_YEARS_EXP

    # Degree / certification
    if _RE_DEGREE_CERT.search(block):
        score += _W_DEGREE_CERT

    # Title word overlap (normalize: lowercase, strip punctuation, ≥4 chars)
    if title_words:
        block_words = frozenset(
            re.sub(r"[^\w]", "", w).lower()
            for w in block.split()
            if len(w) >= 4
        )
        overlap = len(title_words & block_words)
        if overlap >= 2:
            score += _W_TITLE_OVERLAP * 1.5
        elif overlap == 1:
            score += _W_TITLE_OVERLAP

    # Seniority cues
    if _RE_SENIORITY.search(block):
        score += _W_SENIORITY

    # Factual concise bonus: short blocks (< 200 chars) with no we/our
    words = block.split()
    if len(words) <= 30 and not _RE_WE_OUR.search(block):
        score += _W_FACTUAL_CONCISE

    # --- Negative signals (only apply when boilerplate penalty not already hit) ---

    if score > _W_BOILERPLATE / 2:  # i.e. boilerplate penalty not already applied
        # High we/our density in a long block → marketing prose
        we_count = len(_RE_WE_OUR.findall(block))
        if we_count >= 4 and len(words) >= 20:
            score += _W_MARKETING_PROSE

        # Very long flat block with no positive signals (generic filler prose)
        if len(words) > 60 and score < 1.0:
            score += _W_GENERIC_FILLER

    return score


# ---------------------------------------------------------------------------
# Block selection within token budget
# ---------------------------------------------------------------------------


def _select_blocks(
    blocks_with_scores: list[tuple[float, int, str]],
    max_tokens: int,
    token_counter: Callable[[str], int],
) -> list[str]:
    """Select highest-scoring blocks that fit within the token budget.

    Args:
        blocks_with_scores: List of (score, original_index, block_text).
        max_tokens: Maximum tokens available for description text.
        token_counter: Function mapping text → token count.

    Returns:
        Selected blocks in their *original order* (not score order) for
        coherent reading by the embedder.
    """
    # Sort by score descending to greedily pick the best blocks first
    ranked = sorted(blocks_with_scores, key=lambda x: x[0], reverse=True)

    tokens_budget = 0
    selected_indices: set[int] = set()

    for score, idx, block in ranked:
        if score <= _W_BOILERPLATE / 2:
            # Skip blocks with heavy boilerplate penalty
            continue
        block_tokens = token_counter(block)
        if tokens_budget + block_tokens > max_tokens:
            continue  # try smaller blocks in subsequent iterations
        tokens_budget += block_tokens
        selected_indices.add(idx)

    # Restore original order
    selected = [
        block
        for score, idx, block in blocks_with_scores
        if idx in selected_indices
    ]
    # Report actual token count of the joined output (accounts for join separators)
    tokens_used = token_counter("\n".join(selected)) if selected else 0
    return selected, tokens_used


# ---------------------------------------------------------------------------
# LLM cleaner scaffold (Phase 2)
# ---------------------------------------------------------------------------


class LLMJobCleaner(Protocol):
    """Interface for an optional LLM-assisted extractive cleaner.

    Implementations MUST be extractive (preserve original wording), not
    free-form summarizers.  They are only called at ingestion/re-embed time,
    never at query or retrieval time.

    To integrate a Claude-based implementation:
      1. Create a class that satisfies this Protocol.
      2. Call ``register_llm_cleaner(your_instance)`` at app startup.
      3. Set env var ``JOB_EXTRACTOR_LLM_ENABLED=1``.

    Implementation contract:
      - MUST preserve exact wording of requirements, skills, tools, experience.
      - MUST remove marketing fluff, legal text, benefits, application instructions.
      - MUST NOT paraphrase, summarize, or invent content.
      - MUST NOT be called at query/retrieval time.
    """

    def clean(self, description: str, title: str | None) -> str:
        """Return an extractively cleaned version of *description*.

        The returned text should contain only original sentences/bullets from
        the input — no paraphrasing, no hallucinated content.
        """
        ...

    def should_clean(self, description: str) -> bool:
        """Return True if this description warrants LLM cleaning.

        Typical triggers:
          - Word count exceeds ``JOB_EXTRACTOR_LLM_THRESHOLD`` (default 800).
          - Heuristic extraction confidence is low (few high-scoring blocks).

        This method must be cheap — no API calls.
        """
        ...


# Module-level registry (one cleaner at a time; replace to swap implementations)
_llm_cleaner: LLMJobCleaner | None = None

# Read once at import time so tests can override via monkeypatch of os.environ
_LLM_ENABLED: bool = os.environ.get("JOB_EXTRACTOR_LLM_ENABLED", "0") in ("1", "true", "yes")
_LLM_THRESHOLD: int = int(os.environ.get("JOB_EXTRACTOR_LLM_THRESHOLD", "800"))
_DEBUG: bool = os.environ.get("JOB_EXTRACTOR_DEBUG", "0") in ("1", "true", "yes")


def register_llm_cleaner(cleaner: LLMJobCleaner) -> None:
    """Register an LLM cleaner implementation.

    Call at application startup before any embedding work begins.
    Has no effect unless ``JOB_EXTRACTOR_LLM_ENABLED=1``.
    """
    global _llm_cleaner
    _llm_cleaner = cleaner


def get_llm_cleaner() -> LLMJobCleaner | None:
    """Return the registered LLM cleaner, or None if disabled / not registered."""
    if not _LLM_ENABLED:
        return None
    return _llm_cleaner


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------


def extract_high_signal_description(
    description: str,
    title: str | None = None,
    token_counter: Callable[[str], int] | None = None,
    max_tokens: int = _DEFAULT_MAX_DESCRIPTION_TOKENS,
) -> tuple[str, dict]:
    """Extract high-signal text from a job description for embedding.

    Pipeline:
      1. Short descriptions → passthrough (no extraction overhead).
      2. Optional LLM cleaning pass (only if enabled + cleaner registered).
      3. Split into blocks (paragraph-first, sentence fallback for flat text).
      4. Score each block by salience (positive / negative signals).
      5. Greedily select highest-scoring blocks within the token budget.
      6. Return selected blocks in original order.

    Args:
        description: Raw (cleaned) job description text.
        title: Job title, used for title-overlap scoring.
        token_counter: Callable mapping text → token count.  If None, uses
            the ``len(words) * 4/3`` heuristic.
        max_tokens: Maximum tokens for the description portion of embedding
            text.  Defaults to 380 (leaves ~130 tokens for metadata).

    Returns:
        Tuple of (extracted_text, diagnostics).

        diagnostics keys:
          - ``strategy``: "passthrough" | "structured" | "flat"
          - ``blocks_total``: number of blocks before selection
          - ``blocks_selected``: number of blocks kept
          - ``tokens_used``: token count of extracted_text (approx if heuristic)
          - ``block_scores``: list of (score, first_40_chars) for debug logging
    """
    counter = token_counter or _heuristic_token_count

    # ------------------------------------------------------------------
    # 1. Passthrough for short descriptions
    # ------------------------------------------------------------------
    word_count = len(description.split())
    if word_count <= _PASSTHROUGH_WORD_THRESHOLD:
        tokens = counter(description)
        clipped = description
        if tokens > max_tokens:
            # Even short descriptions can exceed budget; word-clip as fallback
            words = description.split()
            while words and counter(" ".join(words)) > max_tokens:
                words = words[:-5]
            clipped = " ".join(words)
        return clipped, {
            "strategy": "passthrough",
            "blocks_total": 1,
            "blocks_selected": 1,
            "tokens_used": counter(clipped),
            "block_scores": [],
        }

    # ------------------------------------------------------------------
    # 2. Optional LLM cleaning pass
    # ------------------------------------------------------------------
    cleaner = get_llm_cleaner()
    if cleaner is not None and cleaner.should_clean(description):
        description = cleaner.clean(description, title)

    # ------------------------------------------------------------------
    # 3. Split into blocks
    # ------------------------------------------------------------------
    blocks, strategy = _split_into_blocks(description)

    if not blocks:
        return description[:500], {
            "strategy": strategy,
            "blocks_total": 0,
            "blocks_selected": 0,
            "tokens_used": counter(description[:500]),
            "block_scores": [],
        }

    # ------------------------------------------------------------------
    # 4. Score each block
    # ------------------------------------------------------------------
    title_words: frozenset[str] = frozenset()
    if title:
        title_words = frozenset(
            re.sub(r"[^\w]", "", w).lower()
            for w in title.split()
            if len(w) >= 4
        )

    blocks_with_scores: list[tuple[float, int, str]] = []
    for idx, block in enumerate(blocks):
        score = _score_block(block, title_words)
        blocks_with_scores.append((score, idx, block))

    if _DEBUG:
        for score, idx, block in sorted(blocks_with_scores, key=lambda x: x[0], reverse=True):
            print(f"  [{score:+.1f}] {block[:80]!r}")

    # ------------------------------------------------------------------
    # 5. Select blocks within token budget
    # ------------------------------------------------------------------
    selected, tokens_used = _select_blocks(blocks_with_scores, max_tokens, counter)

    # ------------------------------------------------------------------
    # 6. Return in original order
    # ------------------------------------------------------------------
    if not selected:
        # Fallback: all blocks were penalised (extremely boilerplate-heavy).
        # Return the single least-bad block (highest score, even if negative)
        # constrained to the token budget.  This is shorter than the full
        # description and avoids returning the most egregious tail sections
        # (benefits, EEO, application instructions).
        best_score, best_idx, best_block = max(blocks_with_scores, key=lambda x: x[0])
        # Clip to token budget if the single block is oversized
        if counter(best_block) > max_tokens:
            words = best_block.split()
            while words and counter(" ".join(words)) > max_tokens:
                words = words[:-5]
            best_block = " ".join(words)
        return best_block, {
            "strategy": strategy,
            "blocks_total": len(blocks),
            "blocks_selected": 0,
            "tokens_used": counter(best_block),
            "block_scores": [(s, b[:40]) for s, _, b in blocks_with_scores],
        }

    extracted = "\n".join(selected)

    diagnostics: dict = {
        "strategy": strategy,
        "blocks_total": len(blocks),
        "blocks_selected": len(selected),
        "tokens_used": tokens_used,
        "block_scores": [(s, b[:40]) for s, _, b in blocks_with_scores],
    }
    return extracted, diagnostics
