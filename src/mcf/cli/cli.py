"""MCF CLI - Command line interface for MyCareersFuture job crawler."""

import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from mcf.matching.service import MatchingService
from mcf.lib.external.client import MCFAPIError
from mcf.lib.crawler.crawler import CrawlProgress
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache
from mcf.lib.embeddings.job_text import build_job_text_from_dict
from mcf.lib.embeddings.resume import extract_resume_text, preprocess_resume_text
from mcf.lib.pipeline.incremental_crawl import run_incremental_crawl
from mcf.lib.sources.cag_source import CareersGovJobSource
from mcf.lib.sources.mcf_source import MCFJobSource
from mcf.lib.storage.base import Storage
from mcf.lib.storage.duckdb_store import DuckDBStore


def _open_store(db: Path | None, db_url: str | None) -> tuple[Storage, str]:
    """Return (store, display_label) based on which option was given.

    Priority: --db-url (Postgres) > --db (DuckDB path) > default DuckDB.
    """
    if db_url:
        from mcf.lib.storage.postgres_store import PostgresStore

        return PostgresStore(db_url), f"Postgres: {db_url[:40]}…"

    db_path = db or Path("data/mcf.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DuckDBStore(str(db_path)), f"DuckDB: {db_path.resolve()}"

app = typer.Typer(
    name="mcf",
    help="MyCareersFuture job crawler CLI",
    rich_markup_mode="rich",
    invoke_without_command=True,
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    """MyCareersFuture job crawler CLI."""
    if ctx.invoked_subcommand is None:
        raise typer.Exit(ctx.get_help())
console = Console()


@app.command("crawl-incremental")
def crawl_incremental(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
    rate_limit: Annotated[
        float,
        typer.Option(
            "--rate-limit",
            "-r",
            help="API requests per second",
        ),
    ] = 4.0,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of jobs to list (for testing)",
        ),
    ] = None,
    categories: Annotated[
        Optional[str],
        typer.Option(
            "--categories",
            help="Comma-separated MCF category names (default: all; ignored for --source cag)",
        ),
    ] = None,
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help="Job source to crawl: mcf | cag | all (default: mcf)",
        ),
    ] = "mcf",
) -> None:
    """Incrementally crawl jobs (fetch job detail only for newly-seen UUIDs).

    Use [bold]--source mcf[/bold] for MyCareersFuture, [bold]--source cag[/bold] for
    Careers@Gov, or [bold]--source all[/bold] to crawl both sequentially.
    """
    valid_sources = {"mcf", "cag", "all"}
    if source not in valid_sources:
        console.print(f"[red]Invalid --source '{source}'. Must be one of: {', '.join(sorted(valid_sources))}[/red]")
        raise typer.Exit(1)

    store, db_display = _open_store(db, db_url)

    console.print(f"[bold cyan]Incremental Crawler[/bold cyan]")
    console.print(f"  Source: [magenta]{source}[/magenta]")
    console.print(f"  Storage: [green]{db_display}[/green]")
    console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow] jobs")
    if categories and source in ("mcf", "all"):
        console.print(f"  Categories (MCF): [yellow]{categories}[/yellow]")
    console.print()

    cats = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

    def _run_source(source_obj, source_label: str, cats_arg=None) -> None:
        """Run incremental crawl for a single source with a progress bar."""
        console.print(f"[bold]Crawling [magenta]{source_label}[/magenta]...[/bold]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Listing {source_label} jobs...", total=None)

            def on_progress(p: CrawlProgress) -> None:
                progress.update(task, total=p.total_jobs, completed=p.fetched)
                if p.current_category:
                    progress.update(
                        task,
                        description=f"[cyan]{p.current_category}[/cyan] ({p.category_index}/{p.total_categories})",
                    )

            result = run_incremental_crawl(
                store=store,
                source=source_obj,
                rate_limit=rate_limit,
                categories=cats_arg,
                limit=limit,
                on_progress=on_progress,
            )

        console.print()
        console.print(f"[bold green]{source_label} crawl complete[/bold green]")
        console.print(f"  Total seen: [cyan]{result.total_seen:,}[/cyan]")
        console.print(f"  Added: [cyan]{len(result.added):,}[/cyan]")
        console.print(f"  Maintained: [cyan]{len(result.maintained):,}[/cyan]")
        console.print(f"  Removed: [cyan]{len(result.removed):,}[/cyan]")
        console.print()

    try:
        if source == "mcf":
            _run_source(MCFJobSource(rate_limit=rate_limit), "MyCareersFuture", cats_arg=cats)
        elif source == "cag":
            _run_source(CareersGovJobSource(rate_limit=rate_limit), "Careers@Gov")
        else:  # "all"
            _run_source(MCFJobSource(rate_limit=rate_limit), "MyCareersFuture", cats_arg=cats)
            _run_source(CareersGovJobSource(rate_limit=rate_limit), "Careers@Gov")
    finally:
        store.close()


@app.command("backfill-rich-fields")
def backfill_rich_fields(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
    rate_limit: Annotated[
        float,
        typer.Option(
            "--rate-limit",
            "-r",
            help="API requests per second (default: 4)",
        ),
    ] = 4.0,
    limit: Annotated[
        Optional[int],
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of jobs to backfill (for batched runs)",
        ),
    ] = None,
) -> None:
    """Backfill rich metadata (categories, employment type, salary, etc.) for existing MCF jobs.

    Fetches job details from the MCF API and updates jobs that have NULL categories_json.
    Run locally; large datasets may take hours. Use --limit for batched runs.
    """
    store, db_display = _open_store(db, db_url)

    try:
        job_uuids = store.get_job_uuids_needing_rich_backfill(limit=limit)
        if not job_uuids:
            console.print("[bold green]No jobs need backfill.[/bold green]")
            return

        console.print(f"[bold cyan]Backfill Rich Fields[/bold cyan]")
        console.print(f"  Storage: [green]{db_display}[/green]")
        console.print(f"  Jobs to backfill: [yellow]{len(job_uuids):,}[/yellow]")
        console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
        if limit:
            console.print(f"  Limit: [yellow]{limit}[/yellow] (batched run)")
        console.print()

        run = store.begin_run(kind="backfill", categories=None)
        source = MCFJobSource(rate_limit=rate_limit)

        ok = 0
        failed = 0
        skipped = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Backfilling...", total=len(job_uuids))

            for job_uuid in job_uuids:
                try:
                    normalized = source.get_job_detail(job_uuid)
                    store.upsert_new_job_detail(
                        run_id=run.run_id,
                        job_uuid=job_uuid,
                        title=normalized.title,
                        company_name=normalized.company_name,
                        location=normalized.location,
                        job_url=normalized.job_url,
                        job_source=normalized.source_id,
                        skills=normalized.skills or None,
                        raw_json=None,
                        categories=normalized.categories or None,
                        employment_types=normalized.employment_types or None,
                        position_levels=normalized.position_levels or None,
                        salary_min=normalized.salary_min,
                        salary_max=normalized.salary_max,
                        posted_date=normalized.posted_date,
                        expiry_date=normalized.expiry_date,
                        min_years_experience=normalized.min_years_experience,
                        description=normalized.description,
                    )
                    ok += 1
                except MCFAPIError as e:
                    if e.status_code == 404:
                        skipped += 1  # Job removed from MCF
                    else:
                        failed += 1
                        progress.console.print(f"[yellow]Warning: {job_uuid}: {e}[/yellow]")
                except Exception as e:
                    failed += 1
                    progress.console.print(f"[yellow]Warning: {job_uuid}: {e}[/yellow]")

                progress.advance(task)

        store.update_daily_stats(run.run_id)
        store.finish_run(
            run.run_id,
            total_seen=len(job_uuids),
            added=ok,
            maintained=0,
            removed=skipped,
        )

        console.print()
        console.print("[bold green]Backfill complete[/bold green]")
        console.print(f"  Updated: [cyan]{ok:,}[/cyan]")
        console.print(f"  Skipped (404): [yellow]{skipped:,}[/yellow]")
        console.print(f"  Failed: [red]{failed:,}[/red]")
    finally:
        store.close()


@app.command("backfill-descriptions")
def backfill_descriptions(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
    rate_limit: Annotated[
        float,
        typer.Option("--rate-limit", "-r", help="API requests per second (default: 4)"),
    ] = 4.0,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", "-l", help="Maximum number of jobs to backfill (for batched runs)"),
    ] = None,
) -> None:
    """Backfill job descriptions for active MCF jobs that have no stored description.

    Fetches each job from the MCF API, strips HTML, and saves the plain-text description.
    Run with --limit for batched runs (e.g. --limit 5000 per day to avoid rate limits).
    """
    store, db_display = _open_store(db, db_url)

    try:
        job_uuids = store.get_job_uuids_needing_description_backfill(limit=limit)
        if not job_uuids:
            console.print("[bold green]No jobs need description backfill.[/bold green]")
            return

        console.print(f"[bold cyan]Backfill Descriptions[/bold cyan]")
        console.print(f"  Storage: [green]{db_display}[/green]")
        console.print(f"  Jobs to backfill: [yellow]{len(job_uuids):,}[/yellow]")
        console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
        if limit:
            console.print(f"  Limit: [yellow]{limit}[/yellow] (batched run)")
        console.print()

        source = MCFJobSource(rate_limit=rate_limit)
        ok = 0
        failed = 0
        skipped = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Backfilling descriptions...", total=len(job_uuids))

            for job_uuid in job_uuids:
                try:
                    normalized = source.get_job_detail(job_uuid)
                    if normalized.description:
                        store.update_job_description(job_uuid, normalized.description)
                        ok += 1
                    else:
                        skipped += 1
                except MCFAPIError as e:
                    if e.status_code == 404:
                        skipped += 1
                    else:
                        failed += 1
                        progress.console.print(f"[yellow]Warning: {job_uuid}: {e}[/yellow]")
                except Exception as e:
                    failed += 1
                    progress.console.print(f"[yellow]Warning: {job_uuid}: {e}[/yellow]")

                progress.advance(task)

        console.print()
        console.print("[bold green]Description backfill complete[/bold green]")
        console.print(f"  Updated: [cyan]{ok:,}[/cyan]")
        console.print(f"  Skipped (no description / 404): [yellow]{skipped:,}[/yellow]")
        console.print(f"  Failed: [red]{failed:,}[/red]")
    finally:
        store.close()


@app.command("backfill-job-daily-stats")
def backfill_job_daily_stats(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
    limit_days: Annotated[
        int,
        typer.Option(
            "--limit-days",
            "-d",
            help="Number of days to backfill (default: 365). Use 0 for full range from data.",
        ),
    ] = 365,
) -> None:
    """One-time backfill of job_daily_stats from the jobs table.

    Populates historical daily stats (active_count, added_count, removed_count) per
    category/employment_type/position_level so dashboard charts show full time series.
    Run once to catch up; the crawler will keep job_daily_stats updated going forward.
    """
    store, db_display = _open_store(db, db_url)

    try:
        console.print("[bold cyan]Backfill job_daily_stats[/bold cyan]")
        console.print(f"  Storage: [green]{db_display}[/green]")
        console.print(f"  Limit: [yellow]{limit_days}[/yellow] days (0 = full range from data)")
        console.print()
        console.print("[cyan]Backfilling...[/cyan] (this may take several minutes)")

        result = store.backfill_job_daily_stats(limit_days=limit_days)

        console.print()
        console.print("[bold green]Backfill complete[/bold green]")
        console.print(f"  Date range: [cyan]{result['date_start']}[/cyan] to [cyan]{result['date_end']}[/cyan]")
        console.print(f"  Rows upserted: [cyan]{result['rows_upserted']:,}[/cyan]")
    finally:
        store.close()


@app.command("process-resume")
def process_resume(
    resume_path: Annotated[
        Path,
        typer.Option("--resume", "-r", help="Path to resume file (default: resume/resume.pdf)"),
    ] = Path("resume/resume.pdf"),
    user_id: Annotated[
        str,
        typer.Option("--user-id", "-u", help="User ID (default: default_user)"),
    ] = "default_user",
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Process resume from file and create profile for matching."""
    store, db_display = _open_store(db, db_url)

    try:
        if not resume_path.exists():
            console.print(f"[bold red]Error:[/bold red] Resume file not found at {resume_path}")
            console.print(f"Please place your resume file at: {resume_path}")
            raise typer.Exit(1)

        console.print(f"[bold cyan]Processing Resume[/bold cyan]")
        console.print(f"  Resume: [green]{resume_path.resolve()}[/green]")
        console.print(f"  User ID: [yellow]{user_id}[/yellow]")
        console.print(f"  Database: [green]{db_display}[/green]")
        console.print()
        
        # Extract resume text
        console.print("[cyan]Extracting resume text...[/cyan]")
        resume_text = extract_resume_text(resume_path)
        console.print(f"[green]Extracted {len(resume_text)} characters[/green]")
        
        # Get or create profile
        profile = store.get_profile_by_user_id(user_id)
        if profile:
            profile_id = profile["profile_id"]
            console.print(f"[cyan]Updating existing profile: {profile_id}[/cyan]")
            store.update_profile(profile_id=profile_id, raw_resume_text=resume_text)
        else:
            import secrets
            profile_id = secrets.token_urlsafe(16)
            console.print(f"[cyan]Creating new profile: {profile_id}[/cyan]")
            store.create_profile(
                profile_id=profile_id,
                user_id=user_id,
                raw_resume_text=resume_text,
            )
        
        # Generate embedding for the resume using the query-side method.
        # BGE models expect a task prefix on the query (resume) side so that
        # the embedding space aligns correctly with passage (job) embeddings.
        console.print("[cyan]Generating embedding...[/cyan]")
        embedder = Embedder(EmbedderConfig())
        preprocessed = preprocess_resume_text(resume_text)
        embedding = embedder.embed_resume(preprocessed)
        store.upsert_candidate_embedding(
            profile_id=profile_id,
            model_name=embedder.model_name,
            embedding=embedding,
        )
        
        console.print()
        console.print("[bold green]Resume processed successfully![/bold green]")
        console.print(f"  Profile ID: [cyan]{profile_id}[/cyan]")
        console.print(f"  You can now use 'mcf match-jobs' to find matching jobs")
    finally:
        store.close()


@app.command("match-jobs")
def match_jobs(
    user_id: Annotated[
        str,
        typer.Option("--user-id", "-u", help="User ID (default: default_user)"),
    ] = "default_user",
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of top matches to return"),
    ] = 25,
    exclude_interacted: Annotated[
        bool,
        typer.Option("--exclude-interacted/--include-interacted", help="Exclude jobs user has interacted with"),
    ] = True,
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Find matching jobs for uploaded resume."""
    store, _ = _open_store(db, db_url)
    
    try:
        # Get profile
        profile = store.get_profile_by_user_id(user_id)
        if not profile:
            console.print(f"[bold red]Error:[/bold red] No profile found for user {user_id}")
            console.print(f"Please run 'mcf process-resume' first")
            raise typer.Exit(1)
        
        profile_id = profile["profile_id"]
        
        console.print(f"[bold cyan]Finding Job Matches[/bold cyan]")
        console.print(f"  User ID: [yellow]{user_id}[/yellow]")
        console.print(f"  Profile ID: [cyan]{profile_id}[/cyan]")
        console.print(f"  Top K: [yellow]{top_k}[/yellow]")
        console.print(f"  Exclude interacted: [yellow]{exclude_interacted}[/yellow]")
        console.print()
        
        # Get matches
        matching_service = MatchingService(store)
        matches, _ = matching_service.match_candidate_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            offset=0,
            exclude_interacted=exclude_interacted,
            user_id=user_id,
        )
        
        if not matches:
            console.print("[yellow]No matches found[/yellow]")
            console.print("Make sure you have:")
            console.print("  1. Processed your resume (mcf process-resume)")
            console.print("  2. Crawled some jobs (mcf crawl-incremental)")
            return
        
        console.print(f"[bold green]Found {len(matches)} matches:[/bold green]")
        console.print()
        
        for i, match in enumerate(matches, 1):
            score = match["similarity_score"]
            semantic = match.get("semantic_score", score)
            skills_overlap = match.get("skills_overlap_score", 0.0)
            matched_skills = match.get("matched_skills") or []
            title = match["title"] or "N/A"
            company = match.get("company_name") or "N/A"
            location = match.get("location") or "N/A"
            job_url = match.get("job_url") or "N/A"

            console.print(f"[bold]{i}. {title}[/bold]")
            console.print(f"   Company: {company}")
            console.print(f"   Location: {location}")
            console.print(f"   Match Score: [green]{score:.2%}[/green]  "
                          f"(semantic: {semantic:.2%}, skills: {skills_overlap:.2%})")
            if matched_skills:
                console.print(f"   Matched Skills: [cyan]{', '.join(matched_skills[:8])}[/cyan]"
                              + (f" +{len(matched_skills) - 8} more" if len(matched_skills) > 8 else ""))
            if job_url != "N/A":
                console.print(f"   URL: [blue]{job_url}[/blue]")
            console.print()
    finally:
        store.close()


@app.command("mark-interaction")
def mark_interaction(
    job_uuid: Annotated[
        str,
        typer.Argument(help="Job UUID to mark as interacted"),
    ],
    interaction_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Interaction type: viewed, dismissed, applied, saved",
        ),
    ],
    user_id: Annotated[
        str,
        typer.Option(
            "--user-id",
            "-u",
            help="User ID (default: default_user)",
        ),
    ] = "default_user",
    db: Annotated[
        Optional[Path],
        typer.Option(
            "--db",
            help="DuckDB file path (default: data/mcf.duckdb)",
        ),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Mark a job as interacted with (viewed, dismissed, applied, etc.)."""
    if interaction_type not in ["viewed", "dismissed", "applied", "saved"]:
        console.print(f"[bold red]Error:[/bold red] Invalid interaction type: {interaction_type}")
        console.print("Valid types: viewed, dismissed, applied, saved")
        raise typer.Exit(1)

    store, db_display = _open_store(db, db_url)

    try:
        # Verify job exists
        job = store.get_job(job_uuid)
        if not job:
            console.print(f"[bold red]Error:[/bold red] Job {job_uuid} not found")
            raise typer.Exit(1)

        store.record_interaction(user_id=user_id, job_uuid=job_uuid, interaction_type=interaction_type)

        console.print(f"[bold green]Interaction recorded[/bold green]")
        console.print(f"  Job: {job.get('title', job_uuid)}")
        console.print(f"  Type: {interaction_type}")
        console.print(f"  User: {user_id}")
        console.print(f"  Storage: [green]{db_display}[/green]")
    finally:
        store.close()


@app.command("reset-ratings")
def reset_ratings_cli(
    user_id: Annotated[
        str,
        typer.Option("--user-id", "-u", help="User ID (default: default_user)"),
    ] = "default_user",
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Reset job interactions and taste profile for a user (for testing)."""
    store, _ = _open_store(db, db_url)
    try:
        result = store.reset_profile_ratings(user_id)
        console.print("[bold green]Reset complete[/bold green]")
        console.print(f"  Interactions deleted: [cyan]{result['interactions_deleted']}[/cyan]")
        console.print(f"  Taste profile: [cyan]{result['taste_deleted']}[/cyan]")
        console.print(f"  Match records: [cyan]{result['matches_deleted']}[/cyan]")
    finally:
        store.close()


@app.command("re-embed")
def re_embed(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL (overrides --db)", envvar="DATABASE_URL"),
    ] = None,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Embedding batch size"),
    ] = 32,
) -> None:
    """Re-embed all jobs with the current model and structured text format.

    Run this once after upgrading the embedding model or pipeline.

    Jobs that were crawled before the structured-text update (and therefore have
    no skills data stored) will be embedded using only their title.  They will
    receive a richer embedding automatically on the next incremental crawl.

    You should also re-run 'mcf process-resume' afterwards so that the
    candidate embedding uses the same model as the jobs.
    """
    if not db_url:
        db_path = db or Path("data/mcf.duckdb")
        if not db_path.exists():
            console.print(f"[bold red]Error:[/bold red] Database not found at {db_path}")
            console.print("Run 'mcf crawl-incremental' first to create the database.")
            raise typer.Exit(1)

    store, db_display = _open_store(db, db_url)
    try:
        all_jobs = store.get_all_active_jobs()
        if not all_jobs:
            console.print("[yellow]No active jobs found in the database.[/yellow]")
            return

        console.print(f"[bold cyan]Re-embedding Jobs[/bold cyan]")
        console.print(f"  Database: [green]{db_display}[/green]")
        console.print(f"  Active jobs: [yellow]{len(all_jobs):,}[/yellow]")
        console.print(f"  Model: [green]{EmbedderConfig().model_name}[/green]")
        console.print(f"  Batch size: [yellow]{batch_size}[/yellow]")
        console.print()

        embeddings_cache = EmbeddingsCache(store=store) if os.getenv("ENABLE_EMBEDDINGS_CACHE", "1") in ("1", "true", "yes") else None
        embedder = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Embedding...", total=len(all_jobs))

            texts: list[str] = []
            uuids: list[str] = []
            embedded = 0

            for job in all_jobs:
                job_text = build_job_text_from_dict(job)

                if not job_text:
                    progress.advance(task)
                    continue

                texts.append(job_text)
                uuids.append(job["job_uuid"])

                if len(texts) >= batch_size:
                    embeddings = embedder.embed_texts(texts)
                    for uuid, emb in zip(uuids, embeddings):
                        store.upsert_embedding(
                            job_uuid=uuid,
                            model_name=embedder.model_name,
                            embedding=emb,
                        )
                    embedded += len(texts)
                    progress.advance(task, len(texts))
                    texts, uuids = [], []

            # Flush remaining
            if texts:
                embeddings = embedder.embed_texts(texts)
                for uuid, emb in zip(uuids, embeddings):
                    store.upsert_embedding(
                        job_uuid=uuid,
                        model_name=embedder.model_name,
                        embedding=emb,
                    )
                embedded += len(texts)
                progress.advance(task, len(texts))

        console.print()
        console.print("[bold green]Re-embedding complete![/bold green]")
        console.print(f"  Jobs re-embedded: [cyan]{embedded:,}[/cyan]")
        console.print()
        console.print("[yellow]Tip:[/yellow] Run 'mcf process-resume' to update your resume "
                      "embedding with the new model.")
    finally:
        store.close()


@app.command("export-to-postgres")
def export_to_postgres(
    db: Annotated[
        Optional[Path],
        typer.Option("--db", help="DuckDB file path (default: data/mcf.duckdb)"),
    ] = None,
    db_url: Annotated[
        str,
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = "",
) -> None:
    """Export job data from DuckDB to PostgreSQL (Supabase).

    Use after a local crawl: crawl to DuckDB, then run this to upload.
    Exports: crawl_runs, jobs, job_run_status, job_embeddings.
    User data (profiles, interactions) is not exported.
    """
    if not db_url:
        console.print("[bold red]Error:[/bold red] --db-url or DATABASE_URL is required")
        raise typer.Exit(1)

    db_path = db or Path("data/mcf.duckdb")
    if not db_path.exists():
        console.print(f"[bold red]Error:[/bold red] DuckDB not found at {db_path}")
        console.print(f"Run 'mcf crawl-incremental --db {db_path}' first.")
        raise typer.Exit(1)

    import duckdb
    from psycopg2.extras import execute_values

    duck_con = duckdb.connect(str(db_path), read_only=True)
    pg_con = __import__("psycopg2").connect(db_url)
    pg_con.autocommit = True

    def pg_cur():
        return pg_con.cursor()

    try:
        # 1. crawl_runs
        rows = duck_con.execute("SELECT run_id, started_at, finished_at, kind, categories_json, total_seen, added, maintained, removed FROM crawl_runs").fetchall()
        if rows:
            with pg_cur() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO crawl_runs(run_id, started_at, finished_at, kind, categories_json, total_seen, added, maintained, removed)
                    VALUES %s ON CONFLICT (run_id) DO NOTHING
                    """,
                    rows,
                )
            console.print(f"[green]crawl_runs:[/green] {len(rows):,} rows")
        else:
            console.print("[yellow]crawl_runs:[/yellow] empty")

        # 2. jobs
        rows = duck_con.execute(
            "SELECT job_uuid, job_source, first_seen_run_id, last_seen_run_id, is_active, first_seen_at, last_seen_at, title, company_name, location, job_url, skills_json FROM jobs"
        ).fetchall()
        if rows:
            with pg_cur() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO jobs(job_uuid, job_source, first_seen_run_id, last_seen_run_id, is_active, first_seen_at, last_seen_at, title, company_name, location, job_url, skills_json)
                    VALUES %s ON CONFLICT (job_uuid) DO NOTHING
                    """,
                    rows,
                )
            console.print(f"[green]jobs:[/green] {len(rows):,} rows")
        else:
            console.print("[yellow]jobs:[/yellow] empty")

        # 3. job_run_status (batch to avoid huge INSERT)
        rows = duck_con.execute("SELECT run_id, job_uuid, status FROM job_run_status").fetchall()
        if rows:
            batch_size = 5000
            with pg_cur() as cur:
                for i in range(0, len(rows), batch_size):
                    batch = rows[i : i + batch_size]
                    execute_values(
                        cur,
                        "INSERT INTO job_run_status(run_id, job_uuid, status) VALUES %s ON CONFLICT (run_id, job_uuid) DO NOTHING",
                        batch,
                    )
            console.print(f"[green]job_run_status:[/green] {len(rows):,} rows")
        else:
            console.print("[yellow]job_run_status:[/yellow] empty")

        # 4. job_embeddings (batch - can be large)
        rows = duck_con.execute("SELECT job_uuid, model_name, embedding_json, dim, embedded_at FROM job_embeddings").fetchall()
        if rows:
            # Detect target schema: embedding_json, embedding (vector), or both
            with pg_cur() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_embeddings' AND column_name IN ('embedding_json', 'embedding')"
                )
                cols = {r[0] for r in cur.fetchall()}
            has_json = "embedding_json" in cols
            has_vector = "embedding" in cols

            if has_json and has_vector:
                insert_sql = "INSERT INTO job_embeddings(job_uuid, model_name, embedding_json, embedding, dim, embedded_at) VALUES %s ON CONFLICT (job_uuid) DO NOTHING"
                template = "(%s, %s, %s, %s::vector, %s, %s)"
                batch_rows = [(r[0], r[1], r[2], r[2], r[3], r[4]) for r in rows]  # emb_json used for both
            elif has_json:
                insert_sql = "INSERT INTO job_embeddings(job_uuid, model_name, embedding_json, dim, embedded_at) VALUES %s ON CONFLICT (job_uuid) DO NOTHING"
                template = None
                batch_rows = rows
            elif has_vector:
                insert_sql = "INSERT INTO job_embeddings(job_uuid, model_name, embedding, dim, embedded_at) VALUES %s ON CONFLICT (job_uuid) DO NOTHING"
                template = "(%s, %s, %s::vector, %s, %s)"
                batch_rows = rows
            else:
                console.print("[bold red]Error:[/bold red] job_embeddings has neither embedding_json nor embedding column. Run scripts/schema.sql first.")
                raise typer.Exit(1)

            batch_size = 1000
            with pg_cur() as cur:
                for i in range(0, len(batch_rows), batch_size):
                    batch = batch_rows[i : i + batch_size]
                    execute_values(cur, insert_sql, batch, template=template if template else None)
            console.print(f"[green]job_embeddings:[/green] {len(rows):,} rows")
        else:
            console.print("[yellow]job_embeddings:[/yellow] empty")

        console.print()
        console.print("[bold green]Export complete![/bold green]")
    finally:
        duck_con.close()
        pg_con.close()


@app.command("db-context")
def db_context(
    db_url: Annotated[
        str,
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = "",
    sample: Annotated[
        int,
        typer.Option("--sample", "-s", help="Sample rows per table (0 to skip)"),
    ] = 3,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Write to file instead of stdout"),
    ] = None,
) -> None:
    """Query Supabase/Postgres schema and data for agent context.

    Outputs markdown with tables, columns, row counts, and optional sample rows.
    Use when building features that touch the database — run this first to get
    schema and sample data context.

    Requires DATABASE_URL or --db-url (Postgres only).
    """
    if not db_url:
        console.print("[bold red]Error:[/bold red] --db-url or DATABASE_URL is required")
        raise typer.Exit(1)

    import psycopg2

    conn = psycopg2.connect(db_url)
    conn.autocommit = True

    lines: list[str] = []

    try:
        with conn.cursor() as cur:
            # Tables in public schema (exclude Supabase internal)
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                  AND table_name NOT LIKE 'pg_%'
                ORDER BY table_name
                """
            )
            tables = [r[0] for r in cur.fetchall()]

        lines.append("# Supabase Database Context")
        lines.append("")
        lines.append(f"*Generated for agent context. Tables: {len(tables)}*")
        lines.append("")

        for table in tables:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    [table],
                )
                cols = cur.fetchall()

                cur.execute("SELECT COUNT(*) FROM " + f'"{table}"')
                count = cur.fetchone()[0]

            lines.append(f"## {table} (n={count:,})")
            lines.append("")
            lines.append("| Column | Type | Nullable |")
            lines.append("|--------|------|----------|")
            for col_name, dtype, nullable in cols:
                lines.append(f"| {col_name} | {dtype} | {nullable} |")
            lines.append("")

            if sample > 0 and count > 0:
                with conn.cursor() as cur:
                    col_list = ", ".join(f'"{c[0]}"' for c in cols)
                    cur.execute(
                        f'SELECT {col_list} FROM "{table}" LIMIT %s',
                        [sample],
                    )
                    rows = cur.fetchall()
                lines.append("**Sample rows:**")
                lines.append("")
                for i, row in enumerate(rows, 1):
                    lines.append(f"### Row {i}")
                    for j, (col_name, dtype, _) in enumerate(cols):
                        val = row[j]
                        if val is not None:
                            s = str(val)
                            if "embedding" in col_name.lower():
                                val = f"<{dtype} len={len(s)}>"
                            elif len(s) > 100:
                                val = s[:97] + "..."
                        lines.append(f"- {col_name}: {val}")
                    lines.append("")
                lines.append("")

        text = "\n".join(lines)

        if output:
            output.write_text(text, encoding="utf-8")
            console.print(f"[green]Wrote database context to {output}[/green]")
        else:
            console.print(text)

    finally:
        conn.close()


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
