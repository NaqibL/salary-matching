"""Tests for the high-signal job description extraction pipeline.

Coverage:
  1. Long description with boilerplate at the front — boilerplate excluded
  2. Description with clear section headers — section blocks score high
  3. Flat description (no newlines) — sentence-level fallback
  4. Boilerplate-heavy text — output shorter than input / low-signal excluded
  5. Token budget clipping — output within max_tokens
  6. Deterministic behavior — identical output on repeated calls
  7. Short description passthrough — "passthrough" strategy returned
  8. LLM path interface — mock cleaner called when conditions match
  9. clean_description() structure preservation — paragraphs separated by newlines
 10. build_job_text_from_normalized() integration — uses improved description
"""

from __future__ import annotations

import os

import pytest

from mcf.lib.embeddings.job_description_extractor import (
    _heuristic_token_count,
    _score_block,
    _split_into_blocks,
    extract_high_signal_description,
    get_llm_cleaner,
    register_llm_cleaner,
)
from mcf.lib.embeddings.job_text import build_job_text_from_normalized
from mcf.lib.sources.base import NormalizedJob, clean_description

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_BOILERPLATE_FRONT = """\
About Us
We are TechCorp Singapore, established in 2008 as a leading provider of IT solutions.
We believe in innovation and work-life balance. Our office is in the CBD. Join us!

Why Join Us
We offer competitive salaries, flexible working arrangements, and annual leave of 18 days.
Medical insurance and dental coverage are included.

Requirements
Minimum 3 years of experience in Python and SQL.
Bachelor's degree in Computer Science or equivalent.
Strong knowledge of AWS and Docker is required.
Experience with Kubernetes is a plus.

Responsibilities
Design and implement scalable data pipelines.
Collaborate with cross-functional teams.
Lead code reviews and mentor junior engineers.
Drive continuous improvement of data infrastructure.

How to Apply
Interested candidates may send their CV to hr@techcorp.sg.
Only shortlisted candidates will be contacted.
"""

_STRUCTURED_SECTIONS = """\
Requirements
- 3+ years of experience in Java and Spring Boot
- Bachelor's degree in Computer Science or related field
- Familiarity with microservices and REST APIs

Responsibilities
- Build and maintain backend services
- Participate in agile ceremonies
- Write unit and integration tests

About the Company
We are a fun and dynamic team that believes in innovation.
Our culture is our strength. Join our exciting journey.
"""

_FLAT_NO_NEWLINES = (
    "We are looking for a senior data engineer with 5+ years of experience. "
    "The role requires strong Python and SQL skills. "
    "You will design ETL pipelines and work with AWS Redshift. "
    "A bachelor's degree in a technical field is preferred. "
    "We offer competitive benefits and flexible working."
)

_BOILERPLATE_HEAVY = """\
About Us
TechCorp is a fast-growing startup. We value our culture and our people.
We believe in work-life balance and making a difference.
Our mission is to disrupt the industry.

Why Join Us
We offer medical insurance, dental coverage, annual leave, and performance bonuses.
Our office is modern and collaborative. We have team lunches and game nights.

How to Apply
Send your CV to hr@techcorp.sg. Only shortlisted candidates will be notified.
We regret that we are unable to provide feedback to all applicants.
"""

_SHORT_DESCRIPTION = "Software engineer role requiring Python and 2 years experience."

_LONG_DESCRIPTION_400W = " ".join(
    [
        "We are looking for a software engineer.",
        "Requirements: 3+ years Python, SQL, AWS.",
        "Bachelor degree in Computer Science preferred.",
        "Responsibilities: build microservices, write tests, review code.",
    ]
    * 40  # repeat to create a long text
)


def _word_token_counter(text: str) -> int:
    """Heuristic token counter (for tests that don't need the real model)."""
    return _heuristic_token_count(text)


# ---------------------------------------------------------------------------
# 1. Long description with boilerplate at front
# ---------------------------------------------------------------------------

class TestBoilerplateAtFront:
    def test_requirements_block_selected(self):
        text, diag = extract_high_signal_description(_BOILERPLATE_FRONT, title="Data Engineer")
        assert "Python" in text or "SQL" in text or "Requirements" in text

    def test_boilerplate_company_excluded(self):
        text, diag = extract_high_signal_description(_BOILERPLATE_FRONT, title="Data Engineer")
        assert "TechCorp Singapore" not in text
        assert "work-life balance" not in text

    def test_apply_block_excluded(self):
        text, diag = extract_high_signal_description(_BOILERPLATE_FRONT, title="Data Engineer")
        assert "hr@techcorp.sg" not in text
        assert "shortlisted" not in text

    def test_strategy_is_structured(self):
        _, diag = extract_high_signal_description(_BOILERPLATE_FRONT)
        assert diag["strategy"] == "structured"

    def test_blocks_selected_fewer_than_total(self):
        _, diag = extract_high_signal_description(_BOILERPLATE_FRONT)
        assert diag["blocks_selected"] < diag["blocks_total"]


# ---------------------------------------------------------------------------
# 2. Description with clear section headers
# ---------------------------------------------------------------------------

class TestSectionHeaders:
    def test_requirements_section_scores_highest(self):
        # Score the "Requirements" block directly
        req_block = "Requirements\n- 3+ years Java\n- Bachelor degree"
        culture_block = "About the Company\nWe are a fun and dynamic team."
        score_req = _score_block(req_block, frozenset())
        score_culture = _score_block(culture_block, frozenset())
        assert score_req > score_culture

    def test_section_header_positive_signal(self):
        block = "Requirements\nMinimum 3 years experience in Python."
        score = _score_block(block, frozenset())
        assert score > 0

    def test_culture_block_negative_score(self):
        block = "About the Company\nWe are a fun and dynamic team. Our culture is our strength."
        score = _score_block(block, frozenset())
        assert score < 0

    def test_output_contains_requirements(self):
        text, _ = extract_high_signal_description(_STRUCTURED_SECTIONS, title="Backend Engineer")
        assert "Java" in text or "Spring Boot" in text or "Requirements" in text

    def test_output_excludes_company_culture(self):
        text, _ = extract_high_signal_description(_STRUCTURED_SECTIONS)
        assert "fun and dynamic" not in text


# ---------------------------------------------------------------------------
# 3. Flat description (no newlines)
# ---------------------------------------------------------------------------

class TestFlatDescription:
    def test_strategy_is_flat(self):
        _, diag = extract_high_signal_description(_FLAT_NO_NEWLINES)
        # Short flat text may use passthrough, longer should be flat
        assert diag["strategy"] in ("flat", "passthrough")

    def test_high_signal_content_preserved(self):
        text, _ = extract_high_signal_description(_FLAT_NO_NEWLINES)
        # At minimum, the Python + years-exp content should appear
        assert "Python" in text or "5+" in text or "data engineer" in text.lower()

    def test_split_fallback_to_sentences(self):
        """_split_into_blocks should use sentence splitting for flat text."""
        blocks, strategy = _split_into_blocks(_FLAT_NO_NEWLINES)
        assert strategy == "flat"
        assert len(blocks) >= 2  # should produce multiple sentence blocks


# ---------------------------------------------------------------------------
# 4. Boilerplate-heavy text
# ---------------------------------------------------------------------------

class TestBoilerplateHeavy:
    def test_output_shorter_than_input(self):
        text, _ = extract_high_signal_description(_BOILERPLATE_HEAVY)
        assert len(text) < len(_BOILERPLATE_HEAVY)

    def test_benefits_excluded(self):
        text, _ = extract_high_signal_description(_BOILERPLATE_HEAVY)
        assert "medical insurance" not in text.lower()
        assert "dental coverage" not in text.lower()

    def test_eeo_excluded(self):
        text, _ = extract_high_signal_description(_BOILERPLATE_HEAVY)
        assert "shortlisted" not in text.lower()

    def test_no_empty_output(self):
        """Even all-boilerplate descriptions must return something (fallback)."""
        text, diag = extract_high_signal_description(_BOILERPLATE_HEAVY)
        assert text.strip()  # never empty

    def test_boilerplate_block_scores_negative(self):
        block = "About Us\nWe are a fast-growing startup that values work-life balance."
        score = _score_block(block, frozenset())
        assert score < 0


# ---------------------------------------------------------------------------
# 5. Token budget clipping
# ---------------------------------------------------------------------------

class TestTokenBudget:
    def test_output_within_budget(self):
        max_tok = 100
        text, diag = extract_high_signal_description(
            _BOILERPLATE_FRONT, max_tokens=max_tok, token_counter=_word_token_counter
        )
        assert _word_token_counter(text) <= max_tok

    def test_tight_budget_returns_something(self):
        text, _ = extract_high_signal_description(
            _BOILERPLATE_FRONT, max_tokens=50, token_counter=_word_token_counter
        )
        assert text.strip()

    def test_tokens_used_reported_correctly(self):
        max_tok = 200
        text, diag = extract_high_signal_description(
            _BOILERPLATE_FRONT, max_tokens=max_tok, token_counter=_word_token_counter
        )
        assert diag["tokens_used"] == _word_token_counter(text)

    def test_large_budget_keeps_more_content(self):
        text_small, _ = extract_high_signal_description(
            _BOILERPLATE_FRONT, max_tokens=50, token_counter=_word_token_counter
        )
        text_large, _ = extract_high_signal_description(
            _BOILERPLATE_FRONT, max_tokens=350, token_counter=_word_token_counter
        )
        assert len(text_large) >= len(text_small)


# ---------------------------------------------------------------------------
# 6. Deterministic behavior
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        results = [
            extract_high_signal_description(_BOILERPLATE_FRONT, title="Engineer")[0]
            for _ in range(5)
        ]
        assert len(set(results)) == 1, "extraction must be deterministic"

    def test_same_flat_input_same_output(self):
        results = [
            extract_high_signal_description(_FLAT_NO_NEWLINES)[0]
            for _ in range(3)
        ]
        assert len(set(results)) == 1

    def test_score_block_deterministic(self):
        block = "Requirements: 3+ years Python, AWS, Docker."
        scores = [_score_block(block, frozenset({"engineer", "data"})) for _ in range(5)]
        assert len(set(scores)) == 1


# ---------------------------------------------------------------------------
# 7. Short description passthrough
# ---------------------------------------------------------------------------

class TestPassthrough:
    def test_short_description_uses_passthrough(self):
        _, diag = extract_high_signal_description(_SHORT_DESCRIPTION)
        assert diag["strategy"] == "passthrough"

    def test_short_description_content_preserved(self):
        text, _ = extract_high_signal_description(_SHORT_DESCRIPTION)
        assert "Python" in text
        assert "2 years" in text

    def test_passthrough_blocks_selected_is_1(self):
        _, diag = extract_high_signal_description(_SHORT_DESCRIPTION)
        assert diag["blocks_selected"] == 1

    def test_passthrough_respects_token_budget(self):
        """Even passthrough must clip if description exceeds budget."""
        long_short = " ".join(["word"] * 200)  # 200 words, ~267 tokens
        text, diag = extract_high_signal_description(
            long_short, max_tokens=50, token_counter=_word_token_counter
        )
        assert _word_token_counter(text) <= 50


# ---------------------------------------------------------------------------
# 8. LLM path interface (mock cleaner)
# ---------------------------------------------------------------------------

class _MockLLMCleaner:
    """Mock LLM cleaner that records calls and returns cleaned text."""

    def __init__(self, threshold: int = 10):
        self.calls: list[tuple[str, str | None]] = []
        self.threshold = threshold

    def clean(self, description: str, title: str | None) -> str:
        self.calls.append((description, title))
        # Simulate extractive cleaning: return only lines with "Requirement"
        lines = description.splitlines()
        kept = [l for l in lines if "Requirement" in l or "require" in l.lower()]
        return "\n".join(kept) if kept else description

    def should_clean(self, description: str) -> bool:
        return len(description.split()) > self.threshold


class TestLLMPathInterface:
    def setup_method(self):
        # Reset the registry before each test
        register_llm_cleaner(None)  # type: ignore[arg-type]

    def test_no_cleaner_registered_returns_none(self, monkeypatch):
        monkeypatch.setenv("JOB_EXTRACTOR_LLM_ENABLED", "0")
        import mcf.lib.embeddings.job_description_extractor as m
        m._LLM_ENABLED = False
        assert get_llm_cleaner() is None

    def test_cleaner_not_called_when_disabled(self, monkeypatch):
        import mcf.lib.embeddings.job_description_extractor as m
        m._LLM_ENABLED = False
        mock = _MockLLMCleaner(threshold=5)
        register_llm_cleaner(mock)
        extract_high_signal_description(_BOILERPLATE_FRONT)
        assert mock.calls == []

    def test_cleaner_called_when_enabled(self, monkeypatch):
        import mcf.lib.embeddings.job_description_extractor as m
        m._LLM_ENABLED = True
        mock = _MockLLMCleaner(threshold=5)
        register_llm_cleaner(mock)
        try:
            extract_high_signal_description(_BOILERPLATE_FRONT, title="Engineer")
            assert len(mock.calls) == 1
            assert mock.calls[0][1] == "Engineer"  # title passed through
        finally:
            m._LLM_ENABLED = False
            register_llm_cleaner(None)  # type: ignore[arg-type]

    def test_should_clean_threshold_respected(self):
        mock = _MockLLMCleaner(threshold=1000)
        assert not mock.should_clean(_BOILERPLATE_FRONT)  # below threshold

        mock2 = _MockLLMCleaner(threshold=5)
        assert mock2.should_clean(_BOILERPLATE_FRONT)  # above threshold


# ---------------------------------------------------------------------------
# 9. clean_description() structure preservation
# ---------------------------------------------------------------------------

class TestCleanDescriptionStructure:
    def test_paragraphs_separated_by_newlines(self):
        raw = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        cleaned = clean_description(raw)
        assert "\n" in cleaned, "paragraph separators should be preserved"

    def test_boilerplate_tail_removed(self):
        raw = "Requirements: Python skills needed.\n\nPDPA notice: By submitting your CV you consent to data processing."
        cleaned = clean_description(raw)
        assert "PDPA" not in cleaned
        assert "Python" in cleaned

    def test_unicode_bullets_normalized(self):
        raw = "• Python\n• SQL\n• AWS"
        cleaned = clean_description(raw)
        assert "•" not in cleaned
        assert "-" in cleaned

    def test_structure_preserved_for_extraction(self):
        """After clean_description, the extractor should see separate blocks."""
        raw = "About Us\nWe are a startup.\n\nRequirements\nPython 3+ years.\n\nBenefits\nMedical insurance."
        cleaned = clean_description(raw)
        # The cleaned text should still have newlines for block splitting
        blocks, strategy = _split_into_blocks(cleaned)
        assert strategy == "structured"
        assert len(blocks) >= 2

    def test_empty_input(self):
        assert clean_description("") == ""
        assert clean_description(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 10. build_job_text_from_normalized() integration
# ---------------------------------------------------------------------------

class TestBuildJobTextIntegration:
    def _make_job(self, description: str) -> NormalizedJob:
        return NormalizedJob(
            source_id="mcf",
            external_id="test-001",
            title="Senior Data Engineer",
            company_name="TechCorp",
            location="Singapore",
            job_url=None,
            skills=["Python", "SQL", "AWS"],
            description=description,
            position_levels=["senior executive"],
            min_years_experience=3,
        )

    def test_output_contains_description_field(self):
        job = self._make_job(_BOILERPLATE_FRONT)
        text = build_job_text_from_normalized(job)
        assert "Description:" in text

    def test_output_contains_title(self):
        job = self._make_job(_BOILERPLATE_FRONT)
        text = build_job_text_from_normalized(job)
        assert "Job Title: Senior Data Engineer" in text

    def test_output_contains_skills(self):
        job = self._make_job(_BOILERPLATE_FRONT)
        text = build_job_text_from_normalized(job)
        assert "Required Skills:" in text
        assert "Python" in text

    def test_boilerplate_not_in_description_field(self):
        job = self._make_job(_BOILERPLATE_FRONT)
        text = build_job_text_from_normalized(job)
        # Extract just the description portion
        desc_part = text.split("Description:", 1)[-1] if "Description:" in text else ""
        assert "work-life balance" not in desc_part
        assert "TechCorp Singapore" not in desc_part

    def test_high_signal_in_description_field(self):
        job = self._make_job(_BOILERPLATE_FRONT)
        text = build_job_text_from_normalized(job)
        desc_part = text.split("Description:", 1)[-1] if "Description:" in text else text
        # Requirements section content should be in the output
        assert "Python" in desc_part or "SQL" in desc_part or "AWS" in desc_part

    def test_custom_token_counter_used(self):
        """Passing a custom token_counter should not raise."""
        call_count = {"n": 0}

        def counting_counter(text: str) -> int:
            call_count["n"] += 1
            return _heuristic_token_count(text)

        job = self._make_job(_BOILERPLATE_FRONT)
        build_job_text_from_normalized(job, token_counter=counting_counter)
        assert call_count["n"] > 0

    def test_none_description_handled(self):
        job = self._make_job(None)  # type: ignore[arg-type]
        text = build_job_text_from_normalized(job)
        assert "Description:" not in text
        assert "Job Title:" in text


# ---------------------------------------------------------------------------
# Scoring unit tests
# ---------------------------------------------------------------------------

class TestScoringSignals:
    def test_years_experience_positive(self):
        score = _score_block("Minimum 3+ years of experience in Python required.", frozenset())
        assert score > 0

    def test_tech_tools_positive(self):
        score = _score_block("Strong knowledge of Python, SQL, and AWS required.", frozenset())
        assert score > 0

    def test_degree_positive(self):
        score = _score_block("Bachelor's degree in Computer Science or equivalent.", frozenset())
        assert score > 0

    def test_benefits_negative(self):
        score = _score_block("We offer medical insurance, dental coverage, and annual leave.", frozenset())
        assert score < 0

    def test_eeo_negative(self):
        score = _score_block("We are an equal opportunity employer.", frozenset())
        assert score < 0

    def test_company_intro_negative(self):
        score = _score_block("About Us: We are a leading IT solutions provider.", frozenset())
        assert score < 0

    def test_title_overlap_bonus(self):
        title_words = frozenset({"data", "engineer", "senior"})
        block = "Looking for a senior data engineer with pipeline experience."
        score_with_title = _score_block(block, title_words)
        score_without = _score_block(block, frozenset())
        assert score_with_title > score_without
