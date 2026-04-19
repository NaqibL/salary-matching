"""Standalone test script: compare heuristic vs LLM job description cleaning.

Modes
-----
No args — run the 4 built-in sample descriptions:
    uv run python scripts/test_llm_cleaner.py

--text "..." — test a single inline description:
    uv run python scripts/test_llm_cleaner.py --text "We are looking for a Python developer..."

--file path/to/desc.txt — test a description from a file:
    uv run python scripts/test_llm_cleaner.py --file ~/Desktop/jobdesc.txt

--from-db N — sample N random jobs from the database and show aggregate stats:
    uv run python scripts/test_llm_cleaner.py --from-db 50
    uv run python scripts/test_llm_cleaner.py --from-db 20 --db data/mcf.duckdb

All modes support LLM cleaning when env vars are set:
    OPENROUTER_API_KEY=sk-or-v1-... JOB_EXTRACTOR_LLM_ENABLED=1 \\
        uv run python scripts/test_llm_cleaner.py --from-db 20

See docs/openrouter-setup.txt for full setup instructions.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows (box-drawing chars in Rich rules)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make sure the src/ package is importable when run from repo root
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))


def _load_dotenv() -> None:
    """Load key=value pairs from .env in the repo root into os.environ.

    Only sets variables that are not already set — existing shell env takes
    precedence so you can still override with: KEY=value uv run python ...
    """
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

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from mcf.lib.embeddings.job_description_extractor import (
    _LLM_ENABLED,
    extract_high_signal_description,
    register_llm_cleaner,
)
from mcf.lib.embeddings.job_text import build_job_text_from_normalized
from mcf.lib.embeddings.llm_cleaner import make_openrouter_cleaner_from_env
from mcf.lib.sources.base import NormalizedJob

console = Console(width=100, legacy_windows=False)

# ---------------------------------------------------------------------------
# Sample job descriptions
# Each is realistic Singapore-market content with a mix of signal + boilerplate.
# ---------------------------------------------------------------------------

SAMPLE_IT = (
    "Software Engineer",
    ["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"],
    ["Senior Executive"],
    3,
    """\
About TechCorp Singapore

TechCorp is a fast-growing fintech startup headquartered in Singapore's CBD. \
We are building the next generation of payment infrastructure for Southeast Asia. \
Our dynamic team of 120+ engineers thrives on innovation, collaboration, and impact. \
We believe in work-life balance, continuous learning, and creating a culture where everyone can thrive.

Why Join Us?

Join a high-energy team that ships features every week. We offer competitive salaries, \
flexible working arrangements, generous annual leave (21 days), full medical and dental coverage, \
monthly team lunches, and an annual learning budget of SGD 2,000.

About the Role

We are looking for a Senior Software Engineer to join our Payments Platform team.

Responsibilities

- Design, build, and maintain high-throughput RESTful APIs using Python and FastAPI.
- Optimise PostgreSQL queries and data models for sub-100ms p99 latency.
- Deploy and monitor microservices on AWS ECS using Docker and Terraform.
- Participate in on-call rotation and incident response.
- Mentor junior engineers and conduct code reviews.

Requirements

- Bachelor's degree in Computer Science, Engineering, or a related field.
- Minimum 3 years of professional software engineering experience.
- Strong proficiency in Python; experience with FastAPI or Django REST Framework.
- Solid understanding of relational databases (PostgreSQL preferred).
- Experience with AWS services (ECS, RDS, S3, CloudWatch).
- Familiarity with Docker, CI/CD pipelines, and Git workflows.
- Strong communication skills and ability to work in an agile team.

Nice to Have

- Experience with event-driven architectures (Kafka, RabbitMQ).
- Knowledge of payment systems or financial regulation in Singapore.

We are an equal opportunity employer. All applications will be treated with strict confidence. \
Only shortlisted candidates will be notified. By submitting your application, you consent to \
the collection and use of your personal data in accordance with our PDPA policy.
""",
)

SAMPLE_FINANCE = (
    "Finance Analyst",
    ["Excel", "SAP", "Financial Modelling", "PowerBI"],
    ["Junior Executive"],
    2,
    """\
Our Story

Founded in 1998, CapitalGroup Singapore has grown from a boutique advisory firm into one \
of Southeast Asia's leading investment management companies. We manage over SGD 8 billion \
in assets across equities, fixed income, and alternative investments. Our mission is to \
deliver consistent, risk-adjusted returns for our clients while upholding the highest \
standards of integrity.

Join Our Team

We are a values-driven organisation that invests in our people. Benefits include competitive \
remuneration, variable bonus, medical and dental insurance, 18 days annual leave, and \
sponsorship for professional qualifications (CFA, ACCA).

Role: Finance Analyst

The Finance Analyst will support the CFO team in financial reporting, budgeting, and \
business performance analysis.

Key Responsibilities

- Prepare monthly management accounts and variance analysis against budget.
- Build and maintain financial models for forecasting and scenario planning.
- Assist in the preparation of board presentations and investor reports.
- Reconcile general ledger accounts and ensure accuracy of financial records.
- Support the annual audit process by liaising with external auditors.
- Analyse business unit P&L and provide actionable insights to senior management.

Requirements

- Degree in Accountancy, Finance, or a related discipline.
- At least 2 years of relevant experience in financial analysis or management reporting.
- Proficiency in Microsoft Excel (pivot tables, VLOOKUP, financial modelling).
- Experience with SAP or similar ERP systems is an advantage.
- Strong analytical and problem-solving skills with high attention to detail.
- CFA Level 1 pass or ACCA qualification preferred.
- Able to work independently and meet tight deadlines.

CapitalGroup is an equal opportunity employer and does not discriminate on the basis of \
race, religion, gender, or national origin. We regret that only shortlisted candidates \
will be notified. Please send your CV and expected salary to careers@capitalgroup.sg.
""",
)

SAMPLE_HEAVY_BOILERPLATE = (
    "Customer Service Executive",
    ["Communication", "CRM", "Microsoft Office"],
    ["Non-Executive"],
    None,
    """\
Who We Are

RetailPros Singapore is an award-winning retail solutions company with a presence in \
12 countries. We are proud to have been voted "Best Workplace 2023" by our employees. \
Our vibrant, inclusive culture is built on three pillars: People, Planet, and Profit.

Our Culture

At RetailPros, we believe that happy employees create happy customers. We foster a \
collaborative, supportive environment where every voice matters. Whether you are just \
starting your career or are a seasoned professional, you will find opportunities to grow \
and thrive here. We celebrate diversity and are committed to building a team that reflects \
the communities we serve.

What We Offer

- Attractive remuneration package with performance bonuses
- 14 days annual leave (increasing to 18 days after 3 years)
- Comprehensive medical and dental benefits
- Staff purchase discounts at all RetailPros outlets
- Annual team-building activities and company retreats
- Structured career development programme and mentorship

The Role

We are looking for a Customer Service Executive to join our friendly team.

What You Will Do

- Respond to customer enquiries via phone, email, and live chat.
- Resolve complaints and escalate complex issues to the relevant department.
- Maintain accurate records of customer interactions in the CRM system.
- Process returns, exchanges, and refunds in accordance with company policy.

What We Are Looking For

- Minimum GCE 'O' Level or equivalent qualification.
- At least 1 year of customer service experience, preferably in retail.
- Proficient in Microsoft Office applications.
- Good communication skills in English; Mandarin is an advantage.
- Patient, empathetic, and solution-oriented.

This is an exciting opportunity to join a fast-growing, innovative company. \
If you are passionate about delivering exceptional customer experiences and want to \
be part of an exciting journey, we would love to hear from you.

Interested candidates, please submit your resume and a cover letter to hr@retailpros.sg. \
We thank all applicants for their interest; only shortlisted candidates will be contacted.
""",
)

SAMPLE_SHORT = (
    "Admin Assistant",
    ["Microsoft Office", "Filing"],
    ["Non-Executive"],
    None,
    """\
Provide administrative support to the office manager. Handle filing, scheduling, and \
correspondence. Proficiency in Microsoft Office required. Min O-Level. 5-day work week.
""",
)

SAMPLES: list[tuple[str, list[str], list[str], int | None, str]] = [
    SAMPLE_IT,
    SAMPLE_FINANCE,
    SAMPLE_HEAVY_BOILERPLATE,
    SAMPLE_SHORT,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _word_count(text: str) -> int:
    return len(text.split())


def _make_normalized(
    title: str,
    skills: list[str],
    position_levels: list[str],
    min_years: int | None,
    description: str,
) -> NormalizedJob:
    return NormalizedJob(
        source_id="mcf",
        external_id="test-0000",
        title=title,
        company_name="Test Co",
        location="Singapore",
        job_url="https://example.com",
        skills=skills,
        description=description,
        position_levels=position_levels,
        min_years_experience=min_years,
    )


def _print_section(label: str, text: str, meta: str = "") -> None:
    meta_str = f"  [dim]{meta}[/dim]" if meta else ""
    console.print(f"\n[bold cyan][{label}][/bold cyan]{meta_str}")
    console.rule(style="dim")
    console.print(text.strip())


def _setup_llm() -> object:
    """Enable LLM cleaning if env vars are present. Returns cleaner or None."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    llm_enabled = os.getenv("JOB_EXTRACTOR_LLM_ENABLED", "0") in ("1", "true", "yes")

    if api_key and llm_enabled:
        cleaner = make_openrouter_cleaner_from_env()
        if cleaner:
            register_llm_cleaner(cleaner)
            import mcf.lib.embeddings.job_description_extractor as _jde
            _jde._LLM_ENABLED = True
            console.print(f"\n[green]LLM cleaning ENABLED[/green] — model: [bold]{cleaner.model}[/bold]")
            return cleaner
    elif api_key and not llm_enabled:
        console.print(
            "\n[yellow]OPENROUTER_API_KEY is set but JOB_EXTRACTOR_LLM_ENABLED is not 1.[/yellow]"
            "\nSet JOB_EXTRACTOR_LLM_ENABLED=1 to enable LLM cleaning."
        )
    else:
        console.print(
            "\n[yellow]LLM cleaning DISABLED[/yellow] — showing heuristic extraction only."
            "\nSee [bold]docs/openrouter-setup.txt[/bold] to enable OpenRouter LLM cleaning."
        )
    return None


def _run_one(
    title: str,
    description: str,
    cleaner,
    skills: list[str] | None = None,
    position_levels: list[str] | None = None,
    min_years: int | None = None,
) -> dict:
    """Run one description through the pipeline. Returns stat dict."""
    words_before = _word_count(description)

    # ── Original ─────────────────────────────────────────────────────────────
    _print_section("ORIGINAL", description, meta=f"{words_before} words")

    # ── Heuristic extraction ──────────────────────────────────────────────────
    extracted, diag = extract_high_signal_description(description, title=title)
    heuristic_meta = (
        f"strategy: {diag['strategy']} | "
        f"blocks: {diag['blocks_total']} → {diag['blocks_selected']} selected | "
        f"~{diag['tokens_used']} tokens"
    )
    _print_section("HEURISTIC EXTRACTION", extracted, meta=heuristic_meta)

    stat = {
        "words_before": words_before,
        "words_after_heuristic": _word_count(extracted),
        "tokens": diag["tokens_used"],
        "strategy": diag["strategy"],
        "llm_latency": None,
        "words_after_llm": None,
        "input_tokens": 0,
        "output_tokens": 0,
    }

    # ── LLM cleaning ─────────────────────────────────────────────────────────
    if cleaner is not None:
        t0 = time.monotonic()
        llm_output = cleaner.clean(description, title=title)
        elapsed = time.monotonic() - t0
        stat["words_after_llm"] = _word_count(llm_output)
        stat["llm_latency"] = elapsed
        stat["input_tokens"] = getattr(cleaner, "last_input_tokens", 0)
        stat["output_tokens"] = getattr(cleaner, "last_output_tokens", 0)
        token_note = f" | in: {stat['input_tokens']} / out: {stat['output_tokens']} tokens" if stat["input_tokens"] else ""
        llm_meta = f"model: {cleaner.model} | {elapsed:.1f}s | {stat['words_after_llm']} words out{token_note}"
        _print_section("LLM CLEANING", llm_output, meta=llm_meta)

    # ── Final embedding text ──────────────────────────────────────────────────
    normalized = _make_normalized(
        title, skills or [], position_levels or [], min_years, description
    )
    final_text = build_job_text_from_normalized(normalized)
    _print_section("FINAL EMBEDDING TEXT", final_text, meta="output of build_job_text_from_normalized()")

    return stat


def _print_stats(stats: list[dict], cleaner) -> None:
    """Print aggregate stats for a batch run."""
    if not stats:
        return

    n = len(stats)
    avg = lambda key: sum(s[key] for s in stats if s[key] is not None) / n

    words_before = [s["words_before"] for s in stats]
    words_heuristic = [s["words_after_heuristic"] for s in stats]
    tokens = [s["tokens"] for s in stats]
    strategies = {}
    for s in stats:
        strategies[s["strategy"]] = strategies.get(s["strategy"], 0) + 1

    console.print()
    console.rule("[bold white] AGGREGATE STATS [/bold white]", style="bright_blue")
    console.print(f"\n  Jobs tested:        [bold]{n}[/bold]")
    console.print(f"  Words before:       avg {sum(words_before)/n:.0f}  "
                  f"(min {min(words_before)}, max {max(words_before)})")
    pct_h = (1 - sum(words_heuristic) / max(sum(words_before), 1)) * 100
    console.print(f"  After heuristic:    avg {sum(words_heuristic)/n:.0f} words  "
                  f"([green]{pct_h:.0f}% reduction[/green])")
    console.print(f"  Avg tokens used:    ~{sum(tokens)/n:.0f}")
    console.print(f"  Strategy breakdown: " +
                  "  ".join(f"{k}: {v}" for k, v in sorted(strategies.items())))

    llm_stats = [s for s in stats if s["words_after_llm"] is not None]
    if llm_stats:
        words_llm = [s["words_after_llm"] for s in llm_stats]
        latencies = [s["llm_latency"] for s in llm_stats]
        pct_l = (1 - sum(words_llm) / max(sum(s["words_before"] for s in llm_stats), 1)) * 100
        console.print(f"\n  LLM cleaned:        {len(llm_stats)}/{n} jobs")
        console.print(f"  After LLM:          avg {sum(words_llm)/len(llm_stats):.0f} words  "
                      f"([green]{pct_l:.0f}% reduction vs original[/green])")
        console.print(f"  Avg LLM latency:    {sum(latencies)/len(latencies):.1f}s")
        console.print(f"  Total LLM time:     {sum(latencies):.1f}s")

        total_input = sum(s["input_tokens"] for s in llm_stats)
        total_output = sum(s["output_tokens"] for s in llm_stats)
        if total_input:
            avg_input = total_input / len(llm_stats)
            avg_output = total_output / len(llm_stats)
            # Pricing: $0.10 / 1M input, $0.40 / 1M output
            input_price_per_m  = 0.10
            output_price_per_m = 0.40
            sample_cost = (total_input * input_price_per_m + total_output * output_price_per_m) / 1_000_000
            console.print(f"\n  [bold]Token usage (this run)[/bold]")
            console.print(f"  Avg input tokens:   {avg_input:.0f}")
            console.print(f"  Avg output tokens:  {avg_output:.0f}")
            console.print(f"  Total input tokens: {total_input:,}")
            console.print(f"  Total output tokens:{total_output:,}")
            console.print(f"  Run cost:           [yellow]${sample_cost:.4f}[/yellow]"
                          f"  [dim](${sample_cost/len(llm_stats)*1000:.4f} per 1,000 jobs)[/dim]")

            console.print(f"\n  [bold]Cost projection @ 2,000 jobs/day[/bold]"
                          f"  [dim](rates: ${input_price_per_m}/1M in, ${output_price_per_m}/1M out)[/dim]")
            for daily_jobs in [2_000]:
                daily_input  = avg_input  * daily_jobs
                daily_output = avg_output * daily_jobs
                daily_cost   = (daily_input * input_price_per_m + daily_output * output_price_per_m) / 1_000_000
                monthly_cost = daily_cost * 30
                console.print(f"  Daily  ({daily_jobs:,} jobs):  [green]${daily_cost:.4f}[/green]")
                console.print(f"  Monthly (30 days):  [green]${monthly_cost:.4f}[/green]")


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------


def run_builtin_samples(cleaner) -> None:
    """Run the 4 hardcoded sample descriptions."""
    stats = []
    for title, skills, position_levels, min_years, description in SAMPLES:
        console.print()
        console.rule(f"[bold white] {title} [/bold white]", style="bright_blue")
        stat = _run_one(title, description, cleaner, skills, position_levels, min_years)
        stats.append(stat)
    _print_stats(stats, cleaner)


def run_text(description: str, title: str, cleaner) -> None:
    """Run a single inline or file description."""
    console.print()
    console.rule(f"[bold white] {title} [/bold white]", style="bright_blue")
    _run_one(title, description, cleaner)


def run_from_db(n: int, db_path: str, cleaner) -> None:
    """Sample n random jobs from the database and run through the pipeline."""
    try:
        import duckdb
    except ImportError:
        console.print("[red]duckdb not installed. Run: uv sync[/red]")
        return

    db_path = db_path or os.getenv("DB_PATH", "data/mcf.duckdb")
    if not Path(db_path).exists():
        console.print(f"[red]Database not found: {db_path}[/red]")
        console.print("Pass --db path/to/mcf.duckdb or set DB_PATH env var.")
        return

    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            """
            SELECT title, description, skills_json, position_levels_json, min_years_experience
            FROM jobs
            WHERE is_active = TRUE
              AND description IS NOT NULL
              AND length(description) > 50
            ORDER BY random()
            LIMIT ?
            """,
            [n],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        console.print("[yellow]No jobs with descriptions found in the database.[/yellow]")
        return

    console.print(f"\n[dim]Sampled {len(rows)} jobs from [bold]{db_path}[/bold][/dim]")

    import json as _json

    stats = []
    for i, (title, description, skills_json, pl_json, min_years) in enumerate(rows, 1):
        skills = _json.loads(skills_json) if skills_json else []
        position_levels = _json.loads(pl_json) if pl_json else []
        title = title or "Untitled"

        console.print()
        console.rule(f"[bold white] [{i}/{len(rows)}] {title} [/bold white]", style="bright_blue")
        stat = _run_one(title, description, cleaner, skills, position_levels, min_years)
        stats.append(stat)

    _print_stats(stats, cleaner)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test heuristic and LLM job description cleaning.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  uv run python scripts/test_llm_cleaner.py\n"
            '  uv run python scripts/test_llm_cleaner.py --text "We need a Python developer..."\n'
            "  uv run python scripts/test_llm_cleaner.py --file ~/Desktop/jobdesc.txt\n"
            "  uv run python scripts/test_llm_cleaner.py --from-db 20\n"
            "  uv run python scripts/test_llm_cleaner.py --from-db 50 --db data/mcf.duckdb\n"
        ),
    )
    parser.add_argument("--text", metavar="TEXT", help="Inline job description text to test.")
    parser.add_argument("--file", metavar="FILE", help="Path to a .txt file containing a job description.")
    parser.add_argument("--title", metavar="TITLE", default="Job", help="Job title for --text / --file mode (default: 'Job').")
    parser.add_argument("--from-db", metavar="N", type=int, help="Sample N random jobs from the database.")
    parser.add_argument("--db", metavar="PATH", default="data/mcf.duckdb", help="DuckDB file path for --from-db (default: data/mcf.duckdb).")
    args = parser.parse_args()

    cleaner = _setup_llm()

    if args.text:
        run_text(args.text, args.title, cleaner)
    elif args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            sys.exit(1)
        run_text(path.read_text(encoding="utf-8"), args.title or path.stem, cleaner)
    elif args.from_db:
        run_from_db(args.from_db, args.db, cleaner)
    else:
        run_builtin_samples(cleaner)

    console.print()
    console.rule(style="dim")
    console.print("\n[dim]Done.[/dim]\n")


if __name__ == "__main__":
    main()
