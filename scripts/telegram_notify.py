"""Daily Telegram digest of new job matches against an interest profile.

Usage
-----
Dry-run (prints digest, does not send):
    uv run python scripts/telegram_notify.py --dry-run

Live (sends to Telegram):
    uv run python scripts/telegram_notify.py

Required env vars:
    DATABASE_URL          Postgres connection string (omit for local DuckDB)
    TELEGRAM_BOT_TOKEN    From BotFather
    TELEGRAM_CHAT_ID      Your personal chat ID

Optional env vars:
    OPENROUTER_API_KEY    Enables LLM seniority check on finalists
    INTEREST_PROFILE_PATH Path to interest profile text (default: scripts/interest_profile.txt)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def _load_dotenv() -> None:
    env_file = _REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

import httpx

from mcf.api.deps import _make_store
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = "google/gemini-2.5-flash-lite"

# Companies excluded regardless of match score (local banks)
_EXCLUDED_COMPANIES = {"ocbc", "united overseas bank", "uob", "maybank", "rhb", "cimb"}

# position_levels values that indicate a senior/management role
_SENIOR_LEVELS = {"senior executive", "manager", "director", "c-suite", "head"}

# predicted_tier values that indicate seniority
_SENIOR_TIERS = {"senior"}


def _load_interest_profile() -> str:
    profile_path = Path(os.environ.get("INTEREST_PROFILE_PATH", _REPO_ROOT / "scripts" / "interest_profile.txt"))
    if not profile_path.exists():
        raise FileNotFoundError(f"Interest profile not found: {profile_path}")
    return profile_path.read_text(encoding="utf-8").strip()


def _is_excluded_company(company_name: str | None) -> bool:
    if not company_name:
        return False
    name_lower = company_name.lower()
    return any(excl in name_lower for excl in _EXCLUDED_COMPANIES)


def _is_senior_by_position_levels(position_levels: list[str]) -> bool:
    if not position_levels:
        return False
    levels_lower = {lvl.lower() for lvl in position_levels}
    # Only exclude if ALL stated levels are senior/management (some postings list multiple)
    return levels_lower.issubset(_SENIOR_LEVELS)


def _llm_seniority_check(title: str, company: str | None, description: str | None, api_key: str) -> bool:
    """Return True if the LLM judges this role is appropriate for 0–2 years experience."""
    snippet = (description or "")[:400]
    user_msg = (
        f"Job title: {title}\n"
        f"Company: {company or 'Unknown'}\n"
        f"Description snippet: {snippet}\n\n"
        "Is this role appropriate for a fresh graduate or someone with 0-2 years of experience? "
        "Internships, temporary attachments, and student programmes should be answered NO.\n"
        "Reply with only: YES or NO"
    )
    payload = {
        "model": _OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": user_msg}],
        "temperature": 0.0,
        "max_tokens": 10,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/mcf-job-matcher",
    }
    try:
        resp = httpx.post(_OPENROUTER_URL, json=payload, headers=headers, timeout=20.0)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().upper()
        return answer.startswith("YES")
    except Exception as exc:
        print(f"  LLM check failed for '{title}': {exc} — keeping job")
        return True  # fail open: keep the job if LLM is unavailable


def _format_salary(salary_min: int | None, salary_max: int | None) -> str:
    if salary_min and salary_max:
        return f"${salary_min:,}–${salary_max:,}/mo"
    if salary_min:
        return f"from ${salary_min:,}/mo"
    if salary_max:
        return f"up to ${salary_max:,}/mo"
    return "Salary undisclosed"


def _format_digest(jobs: list[dict]) -> str:
    today = date.today().isoformat()
    if not jobs:
        return f"No strong matches today ({today})."
    lines = [f"{len(jobs)} new match{'es' if len(jobs) != 1 else ''} — {today}", ""]
    for i, job in enumerate(jobs, 1):
        salary = _format_salary(job.get("salary_min"), job.get("salary_max"))
        company = job.get("company_name") or "Unknown company"
        title = job.get("title") or "Untitled"
        url = job.get("job_url") or ""
        lines.append(f"{i}. {title} · {company} · {salary}")
        if url:
            lines.append(f"   {url}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15.0)
    resp.raise_for_status()


def main(dry_run: bool = False) -> None:
    store = _make_store()
    try:
        print("Loading interest profile...")
        profile_text = _load_interest_profile()

        print("Embedding interest profile (loading BGE model)...")
        embedder = Embedder(EmbedderConfig())
        interest_emb = embedder.embed_query(profile_text)

        print("Fetching new jobs (embedded in last 24h)...")
        new_job_records = store.get_active_jobs_embedded_since(days=1)
        new_uuids: set[str] = {r["job_uuid"] for r in new_job_records}
        position_levels_by_uuid: dict[str, list[str]] = {
            r["job_uuid"]: r["position_levels"] for r in new_job_records
        }
        employment_types_by_uuid: dict[str, list[str]] = {
            r["job_uuid"]: r["employment_types"] for r in new_job_records
        }
        print(f"  {len(new_uuids)} new jobs found")

        if not new_uuids:
            msg = f"No new jobs today ({date.today().isoformat()})."
            print(msg)
            if not dry_run:
                token = os.environ["TELEGRAM_BOT_TOKEN"]
                chat_id = os.environ["TELEGRAM_CHAT_ID"]
                _send_telegram(token, chat_id, msg)
            return

        print("Scoring all active jobs against interest profile...")
        ranked = store.get_active_job_ids_ranked(interest_emb, limit=50_000)

        # Filter to new-only, convert distance to similarity, take top 30
        new_ranked = [
            (uuid, 1.0 - distance)
            for uuid, distance, _ in ranked
            if uuid in new_uuids
        ]
        new_ranked.sort(key=lambda x: x[1], reverse=True)
        top_uuids = [uuid for uuid, _ in new_ranked[:30]]

        print(f"  Top {len(top_uuids)} candidates after interest scoring")

        print("Fetching full job details...")
        jobs = store.get_jobs_by_uuids(top_uuids)

        # Hard filters
        filtered = []
        for job in jobs:
            uuid = job["job_uuid"]
            if _is_excluded_company(job.get("company_name")):
                continue
            if job.get("predicted_tier") in _SENIOR_TIERS:
                continue
            if _is_senior_by_position_levels(position_levels_by_uuid.get(uuid, [])):
                continue
            emp_types = {t.lower() for t in employment_types_by_uuid.get(uuid, [])}
            if "internship" in emp_types:
                continue
            filtered.append(job)

        print(f"  {len(filtered)} jobs after hard filters")

        # LLM seniority check
        api_key = os.environ.get("OPENROUTER_API_KEY")
        finalists: list[dict] = []
        if api_key and filtered:
            print(f"Running LLM seniority check on {min(len(filtered), 15)} jobs...")
            for job in filtered[:15]:
                ok = _llm_seniority_check(
                    job.get("title", ""),
                    job.get("company_name"),
                    job.get("description"),
                    api_key,
                )
                status = "KEEP" if ok else "DROP"
                print(f"  [{status}] {job.get('title')} @ {job.get('company_name')}")
                if ok:
                    finalists.append(job)
        else:
            if not api_key:
                print("OPENROUTER_API_KEY not set — skipping LLM check, keeping all finalists")
            finalists = filtered[:15]

        top_jobs = finalists[:10]
        digest = _format_digest(top_jobs)

        print("\n--- Digest ---")
        print(digest)
        print("--- End ---\n")

        if dry_run:
            print("Dry-run mode — not sending to Telegram.")
            return

        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping send.")
            return

        print("Sending to Telegram...")
        _send_telegram(token, chat_id, digest)
        print("Sent.")

    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Telegram digest of new job matches")
    parser.add_argument("--dry-run", action="store_true", help="Print digest without sending")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
