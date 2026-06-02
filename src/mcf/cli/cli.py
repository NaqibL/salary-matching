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


def _open_store(db_url: str | None) -> tuple[Storage, str]:
    """Return (store, display_label) for the Postgres store."""
    if not db_url:
        console.print("[bold red]Error:[/bold red] --db-url or DATABASE_URL is required")
        raise typer.Exit(1)
    from mcf.lib.storage.postgres_store import PostgresStore

    return PostgresStore(db_url), f"Postgres: {db_url[:40]}…"

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
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
    no_embed: Annotated[
        bool,
        typer.Option(
            "--no-embed",
            help="Skip embedding and classification (store job details only).",
            is_flag=True,
        ),
    ] = False,
) -> None:
    """Incrementally crawl jobs (fetch job detail only for newly-seen UUIDs).

    Use [bold]--source mcf[/bold] for MyCareersFuture, [bold]--source cag[/bold] for
    Careers@Gov, or [bold]--source all[/bold] to crawl both sequentially.
    """
    valid_sources = {"mcf", "cag", "all"}
    if source not in valid_sources:
        console.print(f"[red]Invalid --source '{source}'. Must be one of: {', '.join(sorted(valid_sources))}[/red]")
        raise typer.Exit(1)

    store, db_display = _open_store(db_url)

    console.print(f"[bold cyan]Incremental Crawler[/bold cyan]")
    console.print(f"  Source: [magenta]{source}[/magenta]")
    console.print(f"  Storage: [green]{db_display}[/green]")
    console.print(f"  Rate limit: [yellow]{rate_limit}[/yellow] req/s")
    if limit:
        console.print(f"  Limit: [yellow]{limit}[/yellow] jobs")
    if categories and source in ("mcf", "all"):
        console.print(f"  Categories (MCF): [yellow]{categories}[/yellow]")
    if no_embed:
        console.print(f"  Embeddings: [yellow]disabled[/yellow]")

    # Wire LLM cleaner if configured (only relevant when embed=True)
    if not no_embed:
        from mcf.lib.embeddings.llm_cleaner import GeminiFlashCleaner
        from mcf.lib.embeddings.job_description_extractor import register_llm_cleaner
        import mcf.lib.embeddings.job_description_extractor as _jde
        from mcf.api.config import settings

        if settings.openrouter_api_key and settings.job_extractor_llm_enabled:
            _llm_cleaner = GeminiFlashCleaner(
                api_key=settings.openrouter_api_key,
                model=settings.openrouter_model,
            )
            register_llm_cleaner(_llm_cleaner)
            _jde._LLM_ENABLED = True
            console.print(f"  LLM cleaning: [green]enabled[/green] ({_llm_cleaner.model})")
        else:
            console.print(f"  LLM cleaning: [yellow]disabled[/yellow]")

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
                embed=not no_embed,
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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
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
    store, db_display = _open_store(db_url)

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
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
    store, db_display = _open_store(db_url)

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
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
    store, db_display = _open_store(db_url)

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Process resume from file and create profile for matching."""
    store, db_display = _open_store(db_url)

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Find matching jobs for uploaded resume."""
    store, _ = _open_store(db_url)
    
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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Mark a job as interacted with (viewed, dismissed, applied, etc.)."""
    if interaction_type not in ["viewed", "dismissed", "applied", "saved"]:
        console.print(f"[bold red]Error:[/bold red] Invalid interaction type: {interaction_type}")
        console.print("Valid types: viewed, dismissed, applied, saved")
        raise typer.Exit(1)

    store, db_display = _open_store(db_url)

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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
) -> None:
    """Reset job interactions and taste profile for a user (for testing)."""
    store, _ = _open_store(db_url)
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
    db_url: Annotated[
        Optional[str],
        typer.Option("--db-url", help="PostgreSQL connection URL", envvar="DATABASE_URL"),
    ] = None,
    batch_size: Annotated[
        int,
        typer.Option("--batch-size", "-b", help="Embedding batch size"),
    ] = 32,
    only_unembedded: Annotated[
        bool,
        typer.Option("--only-unembedded", help="Only embed jobs that have no existing embedding"),
    ] = False,
    since_days: Annotated[
        Optional[int],
        typer.Option("--since-days", help="Re-embed active jobs whose embedding was written within the last N days"),
    ] = None,
) -> None:
    """Re-embed all jobs with the current model and structured text format.

    Run this once after upgrading the embedding model or pipeline.

    Jobs that were crawled before the structured-text update (and therefore have
    no skills data stored) will be embedded using only their title.  They will
    receive a richer embedding automatically on the next incremental crawl.

    You should also re-run 'mcf process-resume' afterwards so that the
    candidate embedding uses the same model as the jobs.
    """
    # Wire LLM cleaner if configured
    from mcf.lib.embeddings.llm_cleaner import GeminiFlashCleaner
    from mcf.lib.embeddings.job_description_extractor import register_llm_cleaner
    import mcf.lib.embeddings.job_description_extractor as _jde
    from mcf.api.config import settings

    _llm_cleaner = None
    if settings.openrouter_api_key and settings.job_extractor_llm_enabled:
        _llm_cleaner = GeminiFlashCleaner(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
        )
        register_llm_cleaner(_llm_cleaner)
        _jde._LLM_ENABLED = True

    store, db_display = _open_store(db_url)
    try:
        if since_days is not None:
            try:
                all_jobs = store.get_active_jobs_embedded_since(since_days)
            except NotImplementedError:
                all_jobs = store.get_all_active_jobs()
        elif only_unembedded:
            try:
                all_jobs = store.get_active_jobs_without_embeddings()
            except NotImplementedError:
                all_jobs = store.get_all_active_jobs()
        else:
            all_jobs = store.get_all_active_jobs()
        if not all_jobs:
            console.print("[yellow]No jobs to embed.[/yellow]")
            return

        console.print(f"[bold cyan]Re-embedding Jobs[/bold cyan]")
        console.print(f"  Database: [green]{db_display}[/green]")
        if since_days is not None:
            mode = f"[yellow]embedded in last {since_days} day(s)[/yellow]"
        elif only_unembedded:
            mode = "[yellow]unembedded only[/yellow]"
        else:
            mode = "[yellow]all active[/yellow]"
        console.print(f"  Mode: {mode}")
        console.print(f"  Jobs to embed: [yellow]{len(all_jobs):,}[/yellow]")
        console.print(f"  Model: [green]{EmbedderConfig().model_name}[/green]")
        console.print(f"  Batch size: [yellow]{batch_size}[/yellow]")
        llm_status = f"[green]enabled[/green] ({_llm_cleaner.model})" if _llm_cleaner and _jde._LLM_ENABLED else "[yellow]disabled[/yellow]"
        console.print(f"  LLM cleaning: {llm_status}")
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
            llm_results: list = []
            embedded = 0

            for job in all_jobs:
                job_text, llm_result = build_job_text_from_dict(job)

                if not job_text:
                    progress.advance(task)
                    continue

                texts.append(job_text)
                uuids.append(job["job_uuid"])
                llm_results.append(llm_result)

                if len(texts) >= batch_size:
                    embeddings = embedder.embed_texts(texts)
                    store.upsert_embeddings_batch(
                        model_name=embedder.model_name,
                        rows=list(zip(uuids, embeddings)),
                    )
                    for uuid, lr in zip(uuids, llm_results):
                        if lr is not None:
                            store.update_llm_extracted_fields(
                                uuid,
                                min_years_experience=lr.min_years_experience,
                                llm_fields_json={
                                    "min_years_experience": lr.min_years_experience,
                                    "canonical_skills": lr.canonical_skills,
                                    "inferred_seniority": lr.inferred_seniority,
                                },
                            )
                    embedded += len(texts)
                    progress.advance(task, len(texts))
                    texts, uuids, llm_results = [], [], []

            # Flush remaining
            if texts:
                embeddings = embedder.embed_texts(texts)
                store.upsert_embeddings_batch(
                    model_name=embedder.model_name,
                    rows=list(zip(uuids, embeddings)),
                )
                for uuid, lr in zip(uuids, llm_results):
                    if lr is not None:
                        store.update_llm_extracted_fields(
                            uuid,
                            min_years_experience=lr.min_years_experience,
                            llm_fields_json={
                                "min_years_experience": lr.min_years_experience,
                                "canonical_skills": lr.canonical_skills,
                                "inferred_seniority": lr.inferred_seniority,
                            },
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
