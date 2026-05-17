"""Debug script — sends the single highest-similarity job to Telegram.

Usage:
    uv run python scripts/telegram_debug.py

Required env vars:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Optional:
    DATABASE_URL          (omit for local DuckDB)
    INTEREST_PROFILE_PATH (default: scripts/interest_profile.txt)
"""

from __future__ import annotations

import os
import sys
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
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

import httpx

from mcf.api.deps import _make_store
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15.0)
    resp.raise_for_status()


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
        sys.exit(1)

    profile_path = Path(os.environ.get("INTEREST_PROFILE_PATH", _REPO_ROOT / "scripts" / "interest_profile.txt"))
    profile_text = profile_path.read_text(encoding="utf-8").strip()

    print("Embedding interest profile...")
    embedder = Embedder(EmbedderConfig())
    interest_emb = embedder.embed_query(profile_text)

    store = _make_store()
    try:
        print("Ranking all active jobs...")
        ranked = store.get_active_job_ids_ranked(interest_emb, limit=1)
        if not ranked:
            print("No jobs found in DB.")
            sys.exit(1)

        top_uuid, distance, _ = ranked[0]
        similarity = 1.0 - distance
        jobs = store.get_jobs_by_uuids([top_uuid])
        if not jobs:
            print(f"Could not fetch job {top_uuid}.")
            sys.exit(1)

        job = jobs[0]
        title = job.get("title") or "Untitled"
        company = job.get("company_name") or "Unknown"
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        url = job.get("job_url") or ""

        if salary_min and salary_max:
            salary = f"${salary_min:,}–${salary_max:,}/mo"
        elif salary_min:
            salary = f"from ${salary_min:,}/mo"
        elif salary_max:
            salary = f"up to ${salary_max:,}/mo"
        else:
            salary = "Salary undisclosed"

        msg = (
            f"[DEBUG] Top match (similarity {similarity:.3f})\n\n"
            f"{title} · {company} · {salary}"
        )
        if url:
            msg += f"\n{url}"

        print(f"\n{msg}\n")
        print("Sending to Telegram...")
        _send_telegram(token, chat_id, msg)
        print("Done.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
