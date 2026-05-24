Surface any schema or implementation divergences between the Storage ABC and the Postgres store. Check the following:

1. **Abstract method coverage** — list every `@abstractmethod` in `src/mcf/lib/storage/base.py`. For each one, confirm `PostgresStore` in `src/mcf/lib/storage/postgres_store.py` implements it (not `raise NotImplementedError`). List any gaps.

2. **`ensure_schema()` completeness** — check that every table and column referenced in `postgres_store.py` query methods is actually created in `ensure_schema()`. Flag any column used in a query but missing from the schema setup.

3. **Supabase schema drift** — using `uv run mcf db-context --db-url $DATABASE_URL`, compare the live Supabase table definitions against what `ensure_schema()` expects. Flag any column that exists in one but not the other.

4. **Report format:**
   - Abstract methods not implemented in PostgresStore
   - Columns used in queries but missing from `ensure_schema()`
   - Columns present in live Supabase schema but not in `ensure_schema()` (or vice versa)
