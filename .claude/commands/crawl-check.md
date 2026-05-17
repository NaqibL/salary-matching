Check the current crawl state and job data health. Do the following:

1. Query the `crawl_runs` table for the last 5 runs — report source, start time, jobs added/updated/expired, and any error messages.
2. Report total active vs inactive job counts from the `jobs` table.
3. Check when MCF and CAG each last ran successfully — flag if either source hasn't run in the last 24 hours.
4. Note any jobs that became active in the last crawl run vs how many expired.

If the user asks to run a test crawl, use:
```bash
uv run mcf crawl-incremental --source all --limit 10
```

Use the Storage layer via the CLI or by reading the DuckDB file directly. Do not call external APIs.
