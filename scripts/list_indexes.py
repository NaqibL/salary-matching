"""List all indexes on the jobs/embeddings tables, with size and definition.

Usage: uv run python scripts/list_indexes.py
"""
from __future__ import annotations

import os

import psycopg2

TABLES = ("jobs", "job_embeddings", "candidate_embeddings", "company_aliases")


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.relname AS table_name,
                i.relname AS index_name,
                pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
                pg_get_indexdef(i.oid) AS index_def
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            WHERE t.relname = ANY(%s)
            ORDER BY t.relname, i.relname
            """,
            (list(TABLES),),
        )
        rows = cur.fetchall()

    if not rows:
        print("No indexes found — check DATABASE_URL / table names.")
        return

    current_table = None
    for table_name, index_name, index_size, index_def in rows:
        if table_name != current_table:
            print(f"\n{table_name}")
            print("-" * len(table_name))
            current_table = table_name
        print(f"  {index_name}  ({index_size})")
        print(f"    {index_def}")


if __name__ == "__main__":
    main()
