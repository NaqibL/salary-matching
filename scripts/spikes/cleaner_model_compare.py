"""THROWAWAY SPIKE — run the production job-cleaner prompt through several
OpenRouter models on the same sample of jobs and compare extraction quality,
failures, latency and cost.

Jobs are sampled from the live DB (DATABASE_URL in .env). Pricing is fetched
from the public OpenRouter models endpoint so the table stays current.

Usage (from repo root):
  uv run python scripts/spikes/cleaner_model_compare.py --n 30
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from mcf.lib.embeddings.llm_cleaner import GeminiFlashCleaner  # noqa: E402

MODELS = [
    "google/gemini-2.5-flash-lite",   # current production model
    "openai/gpt-oss-120b",            # best in the 2026-11-01 20-job spike
    "openai/gpt-oss-20b",
    "openai/gpt-5-nano",
    "z-ai/glm-5.3-flash",
    "mistralai/mistral-small-24b-instruct-2501",
    "google/gemma-3-12b-it",
    "google/gemma-4-26b-a4b-it",
    "nvidia/nemotron-3-nano-30b-a3b",
    "meta-llama/llama-3.1-8b-instruct",
]
MAX_FAILURES = 2  # a model failing more than this many of N calls is disqualified


def fetch_pricing() -> dict[str, tuple[float, float]]:
    """Return {slug: ($/M input, $/M output)} from OpenRouter's public listing."""
    data = httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
    return {
        m["id"]: (float(m["pricing"]["prompt"]) * 1e6, float(m["pricing"]["completion"]) * 1e6)
        for m in data
    }


def sample_jobs(n: int, seed: int) -> list[dict]:
    """Pull `n` random active jobs with a real description from Postgres."""
    import psycopg2

    db_url = os.environ["DATABASE_URL"]
    with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT setseed(%s)", [(seed % 1000) / 1000.0])
        cur.execute(
            "SELECT job_uuid, title, description FROM jobs"
            " WHERE is_active = TRUE AND description IS NOT NULL"
            " AND length(description) > 400"
            " ORDER BY random() LIMIT %s",
            [n],
        )
        rows = cur.fetchall()
    return [{"job_uuid": r[0], "title": r[1] or "", "description": r[2]} for r in rows]


def run_model(slug: str, pin: float, pout: float, jobs: list[dict], workers: int) -> dict:
    key = os.environ["OPENROUTER_API_KEY"]

    def one(j):
        c = GeminiFlashCleaner(api_key=key, model=slug, timeout=120)
        t0 = time.perf_counter()
        r = c.clean(j["description"], j["title"])
        dt = time.perf_counter() - t0
        failed = c.last_input_tokens == 0
        return {
            "title": j["title"], "failed": failed, "lat": dt,
            "in": c.last_input_tokens, "out": c.last_output_tokens,
            "years": r.min_years_experience, "skills": r.canonical_skills,
            "sen": r.inferred_seniority,
            "words": len(r.cleaned_text.split()),
            "cleaned_changed": r.cleaned_text.strip() != j["description"].strip(),
            "cleaned": r.cleaned_text,
        }

    t_start = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, jobs))
    wall = time.perf_counter() - t_start
    ok = [r for r in res if not r["failed"]]
    n = len(res)
    tin = sum(r["in"] for r in ok)
    tout = sum(r["out"] for r in ok)
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    lats = sorted(r["lat"] for r in ok)
    return {
        "model": slug, "n": n, "failed": n - len(ok),
        "skills_found": sum(1 for r in ok if r["skills"]),
        "years_found": sum(1 for r in ok if r["years"] is not None),
        "sen_found": sum(1 for r in ok if r["sen"]),
        "rewritten": sum(1 for r in ok if r["cleaned_changed"]),
        "avg_words": round(sum(r["words"] for r in ok) / max(1, len(ok))),
        "p50_lat": round(lats[len(lats) // 2], 1) if lats else None,
        "p90_lat": round(lats[int(len(lats) * 0.9)], 1) if lats else None,
        "wall_s": round(wall, 1),
        "in_tok": tin, "out_tok": tout, "cost": round(cost, 5),
        "per_job": round(cost / max(1, len(ok)), 6),
        "per_1k_jobs": round(cost / max(1, len(ok)) * 1000, 3),
        "rows": res,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--show", type=int, default=2, help="full examples to print for the top models")
    ap.add_argument("--top", type=int, default=2, help="how many top models get full examples")
    ap.add_argument("--models", nargs="*", default=None, help="override model list")
    ap.add_argument("--out", default=None, help="write full results JSON here")
    a = ap.parse_args()

    pricing = fetch_pricing()
    models = a.models or MODELS
    jobs = sample_jobs(a.n, a.seed)
    print(f"{len(jobs)} jobs sampled from DB (seed={a.seed})\n")

    summaries = []
    for slug in models:
        if slug not in pricing:
            print(f"skipping {slug}: not listed on OpenRouter")
            continue
        pin, pout = pricing[slug]
        print(f"running {slug} ...", flush=True)
        s = run_model(slug, pin, pout, jobs, a.workers)
        s["disqualified"] = s["failed"] > MAX_FAILURES
        summaries.append(s)
        print(f"  failed={s['failed']} skills={s['skills_found']} sen={s['sen_found']} "
              f"p50={s['p50_lat']}s cost=${s['cost']}", flush=True)

    total_cost = sum(s["cost"] for s in summaries)
    print("\n=== summary ===")
    hdr = ["model", "failed", "skills_found", "years_found", "sen_found", "rewritten",
           "avg_words", "p50_lat", "p90_lat", "wall_s", "per_1k_jobs"]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for s in summaries:
        flag = " (DISQUALIFIED)" if s["disqualified"] else ""
        print("| " + " | ".join(str(s[h]) + (flag if h == "model" else "") for h in hdr) + " |")
    print(f"\n(counts out of {len(jobs)} jobs; per_1k_jobs is USD; total spend this run ≈ ${total_cost:.3f})")

    # Rank qualified models: fields found first, then cost, then speed
    qualified = [s for s in summaries if not s["disqualified"]]
    qualified.sort(key=lambda s: (-(s["skills_found"] + s["sen_found"] + s["years_found"]),
                                  s["per_job"], s["p50_lat"] or 999))
    print("\n=== ranking (fields found desc, then cost, then speed) ===")
    for i, s in enumerate(qualified, 1):
        print(f"{i}. {s['model']}: fields={s['skills_found'] + s['sen_found'] + s['years_found']} "
              f"${s['per_1k_jobs']}/1k p50={s['p50_lat']}s")

    for s in qualified[: a.top]:
        print(f"\n===== {s['model']} examples =====")
        shown = 0
        for r in s["rows"]:
            if r["failed"]:
                continue
            print(f"--- {r['title']}\n years={r['years']} sen={r['sen']} skills={r['skills']}\n{r['cleaned']}\n")
            shown += 1
            if shown >= a.show:
                break

    print("\n=== seniority per job across models ===")
    print(f"{'title':50} | " + " | ".join(s["model"].split("/")[-1][:14] for s in summaries))
    for i, j in enumerate(jobs):
        print(f"{j['title'][:50]:50} | " + " | ".join(str(s["rows"][i]["sen"]) for s in summaries))

    if a.out:
        Path(a.out).write_text(json.dumps(summaries, indent=1, default=str), encoding="utf-8")
        print(f"\nfull results written to {a.out}")


if __name__ == "__main__":
    main()
