Surface any schema or implementation divergences between the DuckDB and Postgres stores. Check the following:

1. **`ensure_schema()` diff** — compare table definitions and column lists between `src/mcf/lib/storage/duckdb_store.py` and `src/mcf/lib/storage/postgres_store.py`. Flag any column that exists in one but not the other.

2. **Abstract method coverage** — list every `@abstractmethod` in `src/mcf/lib/storage/base.py`. For each one, confirm both stores implement it (not `raise NotImplementedError`). List any gaps.

3. **SQL dialect risks** — look for places where one store uses DuckDB-only syntax (e.g., `RETURNING`, `ARRAY[]`, `json_extract`) without an equivalent in the Postgres store, or vice versa. Common divergence points:
   - Upsert: DuckDB uses `INSERT OR REPLACE`, Postgres uses `INSERT ... ON CONFLICT DO UPDATE`
   - Arrays: DuckDB uses `list_contains()`, Postgres uses `= ANY()`
   - JSON: DuckDB uses `json_extract()`, Postgres uses `->>` operator
   - Vectors: DuckDB uses `array_cosine_similarity()`, Postgres uses `<=>` (pgvector)

4. **Report format:**
   - Columns only in DuckDB store
   - Columns only in Postgres store
   - Methods not implemented in one store
   - SQL patterns that may silently fail if the DB is switched

Refer to `.claude/agents/db-agent.md` for the full dialect difference table before making any fixes.
