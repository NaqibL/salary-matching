# Embeddings (`src/mcf/lib/embeddings/`)

## Purpose

Handles all text-to-vector operations: wrapping the BGE sentence transformer model, extracting clean text from resumes and job postings, and caching embeddings to avoid redundant GPU/CPU inference. This is the ML core of the matching system.

## Key Files

| File | Purpose |
|---|---|
| `base.py` | `EmbedderProtocol` interface |
| `embedder.py` | `Embedder` class — wraps `BAAI/bge-small-en-v1.5`, handles batching, integrates cache |
| `embeddings_cache.py` | `EmbeddingsCache` — LRU in-memory + optional DB-backed cache keyed on content hash |
| `resume.py` | Extracts and preprocesses text from PDF, DOCX, TXT, and MD resume files |
| `job_text.py` | Extracts clean text from job descriptions (strips HTML, normalises whitespace) |

## Dependencies

| Package | Use |
|---|---|
| `sentence-transformers` | BGE model inference |
| `pypdf` | PDF text extraction |
| `python-docx` | DOCX text extraction |
| `lxml` / `beautifulsoup4` | HTML cleaning for job descriptions |
| `numpy` | Embedding arrays |

## Internal Dependencies

- `mcf.lib.storage.base` — optional DB-backed embedding cache
- `mcf.api.config` — model name, cache settings

## Model Details

- **Model**: `BAAI/bge-small-en-v1.5` (384 dimensions, 512 token limit)
- **Auto-downloaded** from Hugging Face on first run to `~/.cache/huggingface/`
- **Asymmetric retrieval**: Resume/query uses the prefix `"Represent this resume for job search: "`, job descriptions are encoded as-is
- **Output**: L2-normalised vectors — dot product equals cosine similarity
- **Batch size**: Configurable (default 32) for throughput during bulk crawls

## Caching Behaviour

`EmbeddingsCache` checks:
1. In-memory LRU cache (fast, bounded by `max_size`)
2. DB cache (if `ENABLE_EMBEDDINGS_CACHE=1`) keyed on `sha256(text)`

Cache hits avoid the ~5-50ms inference cost per embedding. Essential for the nightly crawl which re-processes thousands of unchanged job texts.

## State Management

`Embedder` is a singleton created in the FastAPI lifespan and injected via `Depends(get_embedder)`. The model is loaded once and kept in memory (~50MB).

## Testing

No dedicated tests. Indirectly tested via smoke tests for `/api/matches` and `/api/lowball/check`.

## Common Modifications

- **Add new text type**: Add extraction function here, use `embedder.embed_query(text)` in the route
- **Change model**: Update `EMBEDDER_MODEL` in config; note dimension change requires re-embedding all stored jobs
- **Adjust resume chunking**: Modify `resume.py` — long resumes are split before embedding
