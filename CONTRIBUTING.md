# Contributing

## Getting Started

See `HANDOVER.md` for quick-start setup instructions (Python env, frontend, environment variables).

## Development Workflow

```bash
# Backend
uv run uvicorn mcf.api.server:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Run tests
uv run pytest tests/ -v

# Manual crawl
uv run mcf crawl-incremental --source mcf --limit 100
```

## Code Style

- **Python**: `ruff` for linting, `black` for formatting, `mypy` for type checking
  ```bash
  uv run ruff check src/
  uv run black src/
  uv run mypy src/
  ```
- **TypeScript**: Standard Next.js ESLint config
  ```bash
  cd frontend && npm run lint
  ```

## Making Changes

1. Read the relevant feature README before modifying — each major directory has one
2. If adding a new feature or endpoint, follow the guides in `.ai/common-tasks.md`
3. Run smoke tests before submitting: `uv run pytest tests/ -v`
4. If you add a new module, add it to `.ai/module-index.md`

---

## AI-Assisted Development Guidelines

This project maintains a set of AI-friendly documentation in the `.ai/` directory. When working with AI coding assistants, point them here first to reduce unnecessary file traversal.

### Quick Reference for AI Agents

| Need | File |
|---|---|
| Understand the system | [`.ai/architecture.md`](.ai/architecture.md) |
| Find where something lives | [`.ai/module-index.md`](.ai/module-index.md) |
| Understand code patterns | [`.ai/conventions.md`](.ai/conventions.md) |
| Perform a common operation | [`.ai/common-tasks.md`](.ai/common-tasks.md) |
| Add a file header | [`.ai/file-header-template.md`](.ai/file-header-template.md) |

### Keeping Docs in Sync

Update the AI docs when you:

- [ ] **Add a new module or file** → Add an entry to `.ai/module-index.md`
- [ ] **Add a new API endpoint** → Update the endpoint table in `src/mcf/api/README.md`
- [ ] **Change a core pattern** (state management, error handling, etc.) → Update `.ai/conventions.md`
- [ ] **Add a new common operation** that will be done repeatedly → Add a section to `.ai/common-tasks.md`
- [ ] **Add a new feature area** (new directory under `src/` or `frontend/`) → Create a `README.md` in that directory and add it to the architecture diagram in `.ai/architecture.md`
- [ ] **Change the technology stack** → Update the stack table in `.ai/architecture.md`
- [ ] **Change environment variables** → Update the config table in `.ai/architecture.md` and `.ai/conventions.md`

### What NOT to Put in AI Docs

- Implementation details that are already clear from reading the code
- Git history or change logs (use commit messages for that)
- Anything already in `HANDOVER.md` or `DEPLOYMENT.md`
- Speculative future architecture

The goal is to help AI agents quickly orient without hallucinating — accurate and concise beats comprehensive.
