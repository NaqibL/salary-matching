"""Dump active jobs whose raw above_market_pct exceeds the display cap (150%)
for manual review of clustering/peer-group quality (SGSAL-019).

These are jobs where a k=23 peer-group cluster median doesn't reflect the
job's true pay band (usually high-comp finance/leadership roles landing in a
broader, lower-median cluster). The hot-jobs page caps and reorders around
these at query time; this report is for investigating whether finer-grained
clustering or per-cluster salary-band splitting is warranted later.

Usage:
    uv run python scripts/hot_jobs_outlier_report.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "cluster_analysis_output"
PCT_CAP = 150.0


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")
    cur.execute(
        """
        SELECT j.job_uuid, j.title, j.company_name, j.salary_min, j.salary_max,
               j.hot_jobs_cluster, c.label AS cluster_label,
               (j.llm_fields_json::jsonb ->> 'inferred_seniority') AS seniority,
               p.salary_median AS peer_median, j.above_market_pct
        FROM jobs j
        LEFT JOIN hot_jobs_cluster_centroids c ON c.cluster_id = j.hot_jobs_cluster
        LEFT JOIN hot_jobs_salary_profiles p ON p.cluster_id = j.hot_jobs_cluster
          AND p.seniority = COALESCE((j.llm_fields_json::jsonb ->> 'inferred_seniority'), 'Unknown')
        WHERE j.is_active = TRUE AND j.above_market_pct > %s
        ORDER BY j.above_market_pct DESC
        """,
        (PCT_CAP,),
    )
    cols = [c.name for c in cur.description]
    rows = cur.fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=cols)
    out_path = OUTPUT_DIR / "hot_jobs_outliers.csv"
    df.to_csv(out_path, index=False)
    print(f"{len(df)} jobs above {PCT_CAP}% cap -> {out_path}")


if __name__ == "__main__":
    main()
