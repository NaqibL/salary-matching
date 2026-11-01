"""Step 2 of the fine-tuning pipeline: LLM label extraction.

Reads data/finetune/jobs_sample.jsonl, calls Gemini Flash Lite via OpenRouter
to extract (seniority, function) labels, checkpoints to data/finetune/labels.jsonl.

Already-labeled job_uuids are skipped automatically — safe to re-run after a crash.

Usage:
    uv run python scripts/finetune/label_jobs.py [--workers 20] [--input ...] [--output ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "google/gemini-2.5-flash-lite"

_VALID_SENIORITIES = {"Intern", "Entry", "Mid", "Senior", "Lead", "Manager", "Ambiguous"}
_VALID_SUBFAMILIES = {
    "bi_analyst", "data_analyst", "data_engineer", "data_scientist",
    "ml_engineer", "business_analyst", "data_architect",
}
_VALID_FUNCTIONS = {
    "Engineering & Technology",
    "Data & Analytics",
    "Product & Design",
    "Sales & Marketing",
    "Finance & Accounting",
    "Legal & Compliance",
    "People & HR",
    "Operations & Admin",
    "Supply Chain & Logistics",
    "Healthcare & Allied Health",
    "Science & Research",
    "Customer Service & Support",
    "F&B & Hospitality",
    "Trades & Technical",
    "Education & Training",
    "Retail",
    "Other",
}

_SYSTEM_PROMPT = """\
You classify job postings with three labels. Output ONLY a JSON object — no explanation, no markdown.

SENIORITY — pick exactly one:
- Intern: student internship or vacation work
- Entry: fresh graduate or 0-2 years, no management responsibility (includes roles labelled "Junior")
- Mid: 2-5 years experience, no management responsibility
- Senior: 5+ years experience, deep individual contributor expertise
- Lead: technical or team lead, primarily IC but may mentor others
- Manager: directly manages people, including Directors and VPs
- Ambiguous: genuinely unclear from the posting

FUNCTION — pick exactly one:
- Engineering & Technology: software engineers, DevOps, cloud, QA, IT infrastructure, systems
- Data & Analytics: data engineering, data science, BI, ML/AI, analytics
- Product & Design: product managers, UX/UI designers
- Sales & Marketing: sales, account management, marketing, growth, PR, communications
- Finance & Accounting: finance, accounting, audit, tax, treasury, risk (financial)
- Legal & Compliance: lawyers, compliance officers, legal counsel, contracts, regulatory
- People & HR: HR, recruitment, talent acquisition, learning & development, payroll
- Operations & Admin: operations, strategy, admin, consulting, project management, executive support
- Supply Chain & Logistics: procurement, logistics, warehouse, supply chain, freight, drivers
- Healthcare & Allied Health: doctors, nurses, allied health, pharmacists, clinical, patient care
- Science & Research: lab technicians, research scientists, R&D (non-software)
- Customer Service & Support: call centre, customer support, service desk, helpdesk
- F&B & Hospitality: chefs, cooks, bakers, baristas, restaurant management, F&B service
- Trades & Technical: electricians, plumbers, technicians, mechanics, construction trades
- Education & Training: teachers, tutors, trainers, educators, lecturers
- Retail: retail assistants, beauty consultants, opticians, store staff, visual merchandising
- Other: does not fit any of the above

SUBFAMILY — only set when FUNCTION is "Data & Analytics", otherwise use null:
- bi_analyst: BI analyst, analytics analyst, intelligence analyst roles
- data_analyst: general data analyst, insights analyst, reporting analyst
- data_engineer: data engineering, ETL, pipelines, analytics engineering
- data_scientist: statistical modeling, ML research, applied scientist
- ml_engineer: ML Ops, model deployment, AI/ML engineering
- business_analyst: business analyst, functional analyst, systems analyst
- data_architect: data architect, solutions architect, enterprise architect
- null: other Data & Analytics roles (e.g. BI developer, quant, data steward)

Output format (exactly this, nothing else):
{"seniority": "<value>", "function": "<value>", "subfamily": "<value_or_null>"}\
"""

_USER_TEMPLATE = "Job Title: {title}\n\n{description}"


async def label_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    job: dict,
    api_key: str,
    model: str,
) -> dict | None:
    """Call the LLM for one job. Returns labeled dict or None on failure."""
    description = (job.get("description") or "")[:3000]  # stay within token budget
    user_msg = _USER_TEMPLATE.format(title=job.get("title", ""), description=description)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 60,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/mcf-job-matcher",
    }

    async with semaphore:
        for attempt in range(3):
            try:
                resp = await client.post(_OPENROUTER_URL, json=payload, headers=headers, timeout=30.0)
                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                # Strip markdown code fences if model wraps output
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                parsed = json.loads(raw)
                seniority = parsed.get("seniority", "").strip()
                function = parsed.get("function", "").strip()
                if seniority not in _VALID_SENIORITIES:
                    seniority = "Ambiguous"
                if function not in _VALID_FUNCTIONS:
                    function = "Other"
                raw_subfamily = parsed.get("subfamily")
                if function == "Data & Analytics" and isinstance(raw_subfamily, str):
                    subfamily: str | None = raw_subfamily.strip() if raw_subfamily.strip() in _VALID_SUBFAMILIES else None
                else:
                    subfamily = None
                return {
                    "job_uuid": job["job_uuid"],
                    "seniority": seniority,
                    "function": function,
                    "subfamily": subfamily,
                }
            except Exception as exc:
                if attempt == 2:
                    print(f"\nFailed {job['job_uuid']} after 3 attempts: {exc}")
                    return None
                await asyncio.sleep(2 ** attempt)
    return None


async def run(
    input_path: Path,
    output_path: Path,
    api_key: str,
    model: str,
    n_workers: int,
) -> None:
    # Load already-labeled uuids for resume support.
    # D&A jobs without a subfamily key are NOT marked done — they will be re-labeled
    # to backfill the new field. Duplicates are fine; downstream code uses last-entry-wins.
    done: set[str] = set()
    needs_backfill = 0
    if output_path.exists():
        with output_path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    uuid = row.get("job_uuid")
                    if not uuid:
                        continue
                    if row.get("function") == "Data & Analytics" and "subfamily" not in row:
                        needs_backfill += 1
                        continue  # re-label to add subfamily
                    done.add(uuid)
                except Exception:
                    pass
        print(f"Resuming -- {len(done):,} already labeled, skipping. {needs_backfill:,} D&A jobs queued for subfamily backfill.")

    # Load jobs
    jobs = []
    with input_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                job = json.loads(line)
                if job["job_uuid"] not in done:
                    jobs.append(job)
            except Exception:
                pass

    total = len(jobs)
    print(f"Jobs to label: {total:,}")
    if total == 0:
        print("Nothing to do.")
        return

    semaphore = asyncio.Semaphore(n_workers)
    completed = 0
    failed = 0
    start = time.monotonic()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        with output_path.open("a", encoding="utf-8") as out_f:
            tasks = [label_one(client, semaphore, job, api_key, model) for job in jobs]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result:
                    out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                    out_f.flush()
                    completed += 1
                else:
                    failed += 1

                total_done = completed + failed
                if total_done % 100 == 0 or total_done == total:
                    elapsed = time.monotonic() - start
                    rate = total_done / elapsed if elapsed > 0 else 0
                    eta = (total - total_done) / rate if rate > 0 else 0
                    print(
                        f"  {total_done:,}/{total:,} "
                        f"({100*total_done/total:.1f}%) "
                        f"| {rate:.1f} req/s "
                        f"| ETA {eta/60:.1f} min "
                        f"| failed {failed}",
                        flush=True,
                    )

    elapsed = time.monotonic() - start
    print(f"\nDone. {completed:,} labeled, {failed} failed, {elapsed/60:.1f} min total.")
    print(f"Output: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/finetune/jobs_sample.jsonl")
    parser.add_argument("--output", default="data/finetune/labels.jsonl")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set")

    asyncio.run(run(
        input_path=Path(args.input),
        output_path=Path(args.output),
        api_key=api_key,
        model=args.model,
        n_workers=args.workers,
    ))


if __name__ == "__main__":
    main()
