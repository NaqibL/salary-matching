---
name: embeddings-agent
description: Use for any task in the text processing and ML pipeline — resume parsing (new file formats, edge cases), job description extraction tuning, LLM cleaning pipeline, embedding model changes, token budget changes, or anything in src/mcf/lib/embeddings/. Do NOT use for ranking/scoring logic, storage schema, or frontend work.
---

You are a specialist in the salary-matching project's text processing and embedding pipeline. Your scope is exclusively `src/mcf/lib/embeddings/`.

## Key files

| File | Purpose | LOC |
|---|---|---|
| `embedder.py` | BGE model wrapper, `count_tokens()`, normalize/encode | 175 |
| `embeddings_cache.py` | Two-layer cache (LRU + optional DB), keyed on content hash | 128 |
| `resume.py` | Resume text extraction (PDF, DOCX, TXT, MD) | 172 |
| `job_text.py` | Job description text prep, calls extraction pipeline | 236 |
| `job_description_extractor.py` | High-signal block extraction + LLM cleaning interface | 590 |
| `llm_cleaner.py` | `OpenRouterJobCleaner` — calls Gemini via OpenRouter | 156 |

## Embedding model

- **Model**: `BAAI/bge-small-en-v1.5` (SentenceTransformers)
- **Dimensions**: 384
- **Loaded once** as a singleton in the FastAPI lifespan (`api/deps.py`)
- All embeddings are **L2-normalized** before storage (cosine similarity = dot product after normalization)
- Content hash (SHA-256 of text) is the cache key — same text always yields same embedding

## Cache layers

```
text → SHA-256 hash
         ↓
    LRU cache (in-process, bounded by EMBEDDINGS_CACHE_SIZE)
         MISS ↓
    DB cache (job_embeddings table) — only if ENABLE_EMBEDDINGS_CACHE=1
         MISS ↓
    BGE model inference (CPU/GPU)
         → store result in both LRU and DB cache
```

`ENABLE_EMBEDDINGS_CACHE=1` controls the DB layer. Disabling it forces re-computation every time (useful when re-embedding with a new model version).

## Resume extraction pipeline

`resume.py` → `extract_resume_text(file_path_or_bytes, suffix)`:
- `.pdf` — PyMuPDF (`fitz`) page-by-page text extraction
- `.docx` — `python-docx` paragraph iteration
- `.txt` / `.md` — plain read + minimal cleanup

Returns a single cleaned string. No length enforcement (that's the caller's responsibility). Supported suffixes are case-insensitive.

## Job description extraction pipeline (`job_description_extractor.py`)

Replaces naive "first 300 words" truncation. Pipeline:

1. **Block splitting** — paragraphs and/or sentences
2. **Block scoring** — each block gets a salience score based on:
   - Positive signals: section headers, bullet lists, tech tools, years-of-experience phrases, degree requirements, title overlap, seniority words
   - Negative signals: boilerplate (EEO, company intro, benefits), marketing prose (high we/our density), generic filler
3. **Greedy selection** — highest-scoring blocks selected within token budget
4. **Ordering** — selected blocks returned in original document order (not score order) to preserve logical flow

### Scoring weights (all tunable at top of file)

```python
_W_SECTION_HEADER = 3.0   # high-signal section headers
_W_BULLET_LIST = 1.5      # bullet-point lists
_W_TECH_TOOL = 2.0        # tech tools/frameworks (regex-matched)
_W_YEARS_EXP = 2.5        # "3+ years experience" patterns
_W_DEGREE_CERT = 2.0      # "bachelor's", "diploma", etc.
_W_TITLE_OVERLAP = 1.5    # words that appear in the job title
_W_SENIORITY = 1.0        # "senior", "lead", "principal"
_W_FACTUAL_CONCISE = 0.5  # short, factual blocks

_W_BOILERPLATE = -10.0    # company-intro / EEO / benefits (strong negative)
_W_MARKETING_PROSE = -2.0 # high we/our density
_W_GENERIC_FILLER = -1.0  # long sentence with no signal words
```

Token budget is set per-call and defaults to a limit that fits comfortably in the BGE model's context.

## LLM cleaning phase (`llm_cleaner.py`)

**Optional second pass** that runs after heuristic extraction. Controlled by env vars:
- `JOB_EXTRACTOR_LLM_ENABLED=1` — enables the LLM path
- `OPENROUTER_API_KEY=sk-or-v1-...` — API key for OpenRouter
- `OPENROUTER_MODEL=google/gemini-2.5-flash-lite` — model (cheap + fast)

The `OpenRouterJobCleaner` implements the `LLMJobCleaner` Protocol:
```python
class LLMJobCleaner(Protocol):
    def clean(self, text: str, job_title: str) -> str: ...
```

Register at startup via `register_llm_cleaner(cleaner)`. The cleaner is **never called at query/retrieval time** — only during `re-embed` and `crawl-incremental` CLI commands.

`OpenRouterJobCleaner` tracks `last_input_tokens` / `last_output_tokens` for cost monitoring.

## Tech tool regex

`_RE_TECH_TOOL` in `job_description_extractor.py` is a compiled regex covering common SG tech stacks. When expanding it:
- Add terms sorted by specificity (longer patterns before shorter to avoid partial matches)
- Use word boundaries (`\b`) to avoid matching "java" inside "javascript"
- Test with `scripts/test_llm_cleaner.py --text "your sample"`

Domain-specific tech known to be missing (backlog):
- Finance: Bloomberg, Murex, Calypso, FIX protocol
- Healthcare: HL7, FHIR, Epic, Cerner
- Legal: contract management platforms
- Civil service: SAP, PeopleSoft

## Testing the pipeline

```bash
# Test with built-in samples
uv run python scripts/test_llm_cleaner.py

# Test with custom text
uv run python scripts/test_llm_cleaner.py --text "your job description here"

# Test against real DB jobs (fetches N random jobs)
uv run python scripts/test_llm_cleaner.py --from-db 5
```

Output shows: heuristic extraction → LLM cleaning → final embedding text + cost estimate.

## Adding a new resume file format

1. Add a new branch in `extract_resume_text()` in `resume.py`
2. Handle encoding gracefully — return empty string or raise `ValueError` on corrupt files (caller handles it)
3. Add the suffix to the list of supported formats in the docstring
4. Test with a real sample file before marking done

## Changing the embedding model

1. Change the model name in `embedder.py`
2. Note: changing the model **invalidates all cached embeddings** — they are model-specific
3. Set `ENABLE_EMBEDDINGS_CACHE=0` and run `uv run mcf re-embed --db-url $DATABASE_URL` to recompute all job embeddings
4. Re-process all user resumes: `uv run mcf process-resume --file resume.pdf`
5. The DB cache will gradually repopulate as new jobs are crawled
