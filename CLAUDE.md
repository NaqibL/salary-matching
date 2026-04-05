# MCF Job Matcher — AI Agent Guide

Before making any changes, read the relevant doc from `.ai/`:

| Task | Read first |
|---|---|
| New to this codebase | `.ai/architecture.md` |
| Finding where something lives | `.ai/module-index.md` |
| Understanding code patterns | `.ai/conventions.md` |
| Adding endpoints, pages, components, etc. | `.ai/common-tasks.md` |
| Writing a file header | `.ai/file-header-template.md` |

Each major directory also has its own `README.md` with endpoint tables, dependencies, and modification guides.

## Key facts

- **Backend**: FastAPI (Python 3.13, `uv`) at `src/mcf/`. Run: `uv run uvicorn mcf.api.server:app --reload`
- **Frontend**: Next.js 14 App Router at `frontend/`. Run: `cd frontend && npm run dev`
- **DB**: DuckDB locally (`data/mcf.duckdb`), Postgres in prod — switched by `DATABASE_URL` env var
- **All DB access** goes through the `Storage` interface (`src/mcf/lib/storage/base.py`) — never import `DuckDBStore`/`PostgresStore` directly in routes
- **All frontend API calls** go through `frontend/lib/api.ts` — never call axios/fetch directly in components
- **Tests**: `uv run pytest tests/ -v` — smoke tests only, real DuckDB, no mocks

## When you finish a change

If you added a new module or changed a core pattern, update the relevant `.ai/` doc so it stays accurate.
