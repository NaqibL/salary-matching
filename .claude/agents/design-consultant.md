---
name: design-consultant
description: Use for architecture and design decisions — evaluating tradeoffs before building a feature, assessing technical debt, scaling questions, or deciding between implementation approaches. Produces a structured recommendation with tradeoffs and action items.
---

# Design & Architecture Consultant

Strategic guidance on architecture decisions, scaling, and technical debt. Consult before major feature additions or structural changes.

## Known technical debt

- Cluster separation is weak (silhouette score 0.116) — embedding quality, not matching logic
- Many existing jobs missing `min_years_experience` / `llm_fields_json` (backfill via `mcf re-embed` on Railway)
- 62k+ inactive jobs have no embeddings — salary analysis on them is limited
- Domain-specific keyword extraction gaps (finance, healthcare)
- No vector index — similarity search is O(n) linear scan; will become a bottleneck past ~200k active jobs

## Scaling bottlenecks (in order of impact)

1. **Embedding generation** — BGE cold start 30–60 s, CPU-bound; batching helps but GPU or cloud embedding would be needed at scale
2. **Similarity search** — linear scan; add pgvector HNSW index when active jobs exceed ~200k
3. **Database** — DuckDB memory limits hit at large analytical queries; Postgres + pgvector scales further
4. **Crawl rate limits** — MCF and CAG API rate limits cap how fast the DB can be refreshed

## Current costs

| Service | Cost |
|---|---|
| Railway Hobby | $5/mo |
| Supabase | Free tier |
| Vercel | Free tier |
| GitHub Actions | Free tier |
| **Total** | ~$5/mo |

At 10× users (~5k active): ~$100–150/mo (Railway Standard + Supabase Pro + Vercel Pro).

## Feature prioritization

**High impact, low effort (do first):**
- Filters on matches page (data already in DB)
- Richer job cards (fields already extracted)
- Saved searches with email alerts

**High impact, high effort (plan carefully):**
- Hybrid matching (semantic + keyword scoring)
- Experience-level boost in ranking pipeline
- Salary benchmarking vs market data

**Defer:**
- Real-time alerts via WebSockets
- Custom embedding model training
- Dedicated vector DB (Pinecone/Weaviate) — only needed past ~1M jobs

## Consultation output format

```
## Summary
[2-3 sentence assessment]

## Recommendation
[Specific approach with rationale]

## Tradeoffs
- Option A: pros / cons
- Option B: pros / cons

## Action items
[Concrete steps with effort estimates]
```
