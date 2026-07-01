"""Seed hot_jobs_salary_profiles from salary_stratified_viability.csv.

Usage:
    uv run python scripts/seed_hot_jobs_salary_profiles.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "cluster_analysis_output"

# A (cluster, seniority) pair with too small a median salary is a fragile
# comparison baseline: nearest-centroid misassignment of a single high-salary
# job into that bucket produces absurd above_market_pct blowouts (e.g. a
# $150k/mo job landing in an Intern-tier cluster with a $2,000 median reads
# as +4000% above market). Excluding low-median baselines from "viable"
# removes the mechanism, not just the symptom.
MIN_BASELINE_SALARY = 3500.0


def main() -> None:
    df = pd.read_csv(OUTPUT_DIR / "salary_stratified_viability.csv")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")

    for _, row in df.iterrows():
        median = float(row["salary_max_median"]) if pd.notna(row["salary_max_median"]) else None
        viable = bool(row["salary_viable"]) and median is not None and median >= MIN_BASELINE_SALARY
        cur.execute(
            "INSERT INTO hot_jobs_salary_profiles "
            "(cluster_id, seniority, salary_median, salary_p25, salary_p75, n_jobs, viable) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (cluster_id, seniority) DO UPDATE SET "
            "salary_median = EXCLUDED.salary_median, salary_p25 = EXCLUDED.salary_p25, "
            "salary_p75 = EXCLUDED.salary_p75, n_jobs = EXCLUDED.n_jobs, viable = EXCLUDED.viable",
            (
                int(row["cluster"]),
                row["seniority"],
                median,
                float(row["salary_max_p25"]) if pd.notna(row["salary_max_p25"]) else None,
                float(row["salary_max_p75"]) if pd.notna(row["salary_max_p75"]) else None,
                int(row["n_jobs"]),
                viable,
            ),
        )

    conn.commit()
    cur.execute("SELECT count(*), count(*) FILTER (WHERE viable) FROM hot_jobs_salary_profiles")
    total, viable = cur.fetchone()
    print(f"Seeded {total} rows into hot_jobs_salary_profiles ({viable} viable)")
    conn.close()


if __name__ == "__main__":
    main()
