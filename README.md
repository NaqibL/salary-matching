# mcf

MyCareersFuture job crawler and matcher for Singapore — local or hosted.

**New?** Start with [HANDOVER.md](HANDOVER.md).

## Features

- Incremental crawling of MyCareersFuture + Careers@Gov listings
- Semantic resume matching (BGE embeddings, cosine similarity + recency decay)
- Taste profiles — rate jobs to build a preference embedding
- Interaction tracking (viewed, applied, dismissed, saved)
- Analytics dashboard (active jobs, categories, salary distribution)
- DuckDB locally; PostgreSQL + Supabase for hosted use

## Quick Start (local)

```bash
# 1. Install dependencies
uv sync
cd frontend && npm install && cd ..

# 2. Place resume
mkdir resume
# copy resume.pdf (or .docx / .txt / .md) into resume/

# 3. Process resume
uv run mcf process-resume

# 4. Crawl jobs
uv run mcf crawl-incremental

# 5. Start servers
uv run uvicorn mcf.api.server:app --reload --port 8000   # terminal 1
cd frontend && npm run dev                                # terminal 2
# Open http://localhost:3000
```

Copy `.env.example` to `.env` — defaults work out of the box for local dev.

## CLI reference

```bash
# Crawl
uv run mcf crawl-incremental                          # MCF (default)
uv run mcf crawl-incremental --source cag             # Careers@Gov
uv run mcf crawl-incremental --source all             # both
uv run mcf crawl-incremental --limit 50               # test run
uv run mcf crawl-incremental --db-url $DATABASE_URL   # Postgres

# Resume & matching
uv run mcf process-resume
uv run mcf process-resume --resume path/to/file.pdf
uv run mcf match-jobs
uv run mcf match-jobs --top-k 50 --include-interacted

# Interactions
uv run mcf mark-interaction <uuid> --type viewed
uv run mcf mark-interaction <uuid> --type applied
uv run mcf mark-interaction <uuid> --type dismissed
uv run mcf mark-interaction <uuid> --type saved

# Database utilities
uv run mcf re-embed                                   # batch re-embed all jobs
uv run mcf export-to-postgres --db-url $DATABASE_URL  # DuckDB → Postgres
uv run mcf backfill-rich-fields                       # fetch salary/category from API
```

For MCF category segmentation (5-run strategy): [docs/CRAWL_STRATEGY.md](docs/CRAWL_STRATEGY.md).
For local crawl → export workflow: [scripts/LOCAL_CRAWL_WORKFLOW.md](scripts/LOCAL_CRAWL_WORKFLOW.md).
For backfill details: [scripts/BACKFILL_README.md](scripts/BACKFILL_README.md).

## Deployment (~$5/month)

| Service | Cost | Purpose |
|---------|------|---------|
| Supabase | Free | Postgres, Auth, Storage |
| Railway Hobby | $5/mo | FastAPI (always-on) |
| Vercel | Free | Next.js frontend |
| GitHub Actions | Free | Daily crawl cron |

See [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step instructions.

## Development

```bash
# Add a Python dependency
uv add <package>
# Then regenerate requirements.txt (used by Dockerfile.api):
uv pip compile pyproject.toml -o requirements.txt

# Add a dev dependency
uv add --dev <package>

# Run tests
uv run pytest tests/ -v
```

`pyproject.toml` + `uv.lock` are the source of truth for Python deps. `requirements.txt` is auto-generated for Docker — do not hand-edit.

## License

MIT
