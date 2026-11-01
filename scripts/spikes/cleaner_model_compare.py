"""THROWAWAY SPIKE — run the production GeminiFlashCleaner prompt through several
OpenRouter models on the same sample jobs and compare extraction quality + cost.

Usage (from repo root):
  uv run python <scratchpad>/cleaner_model_compare.py --n 20
"""
from __future__ import annotations

import argparse, json, random, sys, time, os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\Users\Luqman\Desktop\projects\salary-matching")
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from mcf.lib.embeddings.llm_cleaner import GeminiFlashCleaner  # noqa: E402

# (slug, $/M input, $/M output)
MODELS = [
    ("google/gemini-2.5-flash-lite", 0.10, 0.40),
    ("z-ai/glm-5.3-flash", 0.013, 0.158),
    ("openai/gpt-oss-120b", 0.026, 0.097),
    ("qwen/qwen3.7-flash", 0.03, 0.13),
]


def sample_jobs(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    with open(ROOT / "data/finetune/jobs_sample.jsonl", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i > 20000:
                break
            d = json.loads(line)
            if d.get("description") and len(d["description"]) > 400:
                rows.append(d)
    return rng.sample(rows, n)


def run_model(slug: str, pin: float, pout: float, jobs: list[dict]) -> dict:
    key = os.environ["OPENROUTER_API_KEY"]

    def one(j):
        c = GeminiFlashCleaner(api_key=key, model=slug, timeout=90)
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

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, jobs))
    ok = [r for r in res if not r["failed"]]
    n = len(res)
    tin = sum(r["in"] for r in ok); tout = sum(r["out"] for r in ok)
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    return {
        "model": slug, "n": n, "failed": n - len(ok),
        "skills_found": sum(1 for r in ok if r["skills"]),
        "years_found": sum(1 for r in ok if r["years"] is not None),
        "sen_found": sum(1 for r in ok if r["sen"]),
        "rewritten": sum(1 for r in ok if r["cleaned_changed"]),
        "avg_words": round(sum(r["words"] for r in ok) / max(1, len(ok))),
        "p50_lat": round(sorted(r["lat"] for r in ok)[len(ok) // 2], 1) if ok else None,
        "in_tok": tin, "out_tok": tout, "cost": round(cost, 5),
        "per_job": round(cost / max(1, len(ok)), 6),
        "rows": res,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show", type=int, default=2, help="print this many full examples per model")
    a = ap.parse_args()
    jobs = sample_jobs(a.n, a.seed)
    print(f"{len(jobs)} jobs\n")
    summaries = []
    for slug, pin, pout in MODELS:
        print(f"running {slug} ...", flush=True)
        s = run_model(slug, pin, pout, jobs)
        summaries.append(s)
    print("\n=== summary ===")
    hdr = ["model", "failed", "skills_found", "years_found", "sen_found", "rewritten", "avg_words", "p50_lat", "cost", "per_job"]
    print(" | ".join(hdr))
    for s in summaries:
        print(" | ".join(str(s[h]) for h in hdr))
    print(f"\n(all counts out of {len(jobs)} jobs)")
    for s in summaries:
        print(f"\n===== {s['model']} examples =====")
        for r in s["rows"][: a.show]:
            print(f"--- {r['title']}\n years={r['years']} sen={r['sen']} skills={r['skills']}\n {r['cleaned'][:700]}\n")
    # per-job seniority agreement across models
    print("\n=== seniority per job across models ===")
    for i, j in enumerate(jobs):
        print(f"{j['title'][:50]:50} | " + " | ".join(str(s['rows'][i]['sen']) for s in summaries))


if __name__ == "__main__":
    main()
