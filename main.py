from datetime import datetime, timezone

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

import aggregators.code_quality as code_quality_agg
import aggregators.multiplier as multiplier_agg
import aggregators.reliability as reliability_agg
import attribution as attribution_engine
import collectors.datadog as dd_collector
import collectors.github as gh_collector
import config as config_loader
import narrative
import report

console = Console()


@click.group()
def cli():
    pass


@cli.command()
@click.option("--from", "from_date", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--to", "to_date", required=True, help="End date (YYYY-MM-DD)")
@click.option("--contributor", default=None, help="Filter to a single contributor email")
@click.option("--config", "config_path", default="harness.config.toml", show_default=True)
@click.option("--output", default=None, help="Override output directory from config")
def run(from_date: str, to_date: str, contributor: str | None, config_path: str, output: str | None):
    """Generate contribution impact reports for a date range."""
    cfg = config_loader.load(config_path)
    output_dir = output or cfg.output.path

    since = _parse_date(from_date)
    until = _parse_date(to_date)
    generated_on = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Collecting GitHub data...", total=None)
        github_data = gh_collector.collect(cfg.github.token, cfg.github.repos, since, until)
        progress.update(task, description=f"GitHub: {len(github_data.commits)} commits, {len(github_data.pull_requests)} PRs")

        task = progress.add_task("Collecting Datadog metrics...", total=None)
        datadog_data = dd_collector.collect(cfg.datadog.api_key, cfg.datadog.app_key, cfg.datadog.dashboards, since, until)
        progress.update(task, description=f"Datadog: {len(datadog_data.metrics)} metrics")

        task = progress.add_task("Building attribution map...", total=None)
        attr_map = attribution_engine.build(github_data, datadog_data, cfg.service_map)
        progress.update(task, description="Attribution complete")

    # Determine contributor set
    all_authors: dict[str, str] = {}  # email -> name
    for c in github_data.commits:
        if c.author_email and c.author_email not in all_authors:
            all_authors[c.author_email] = c.author_name
    for pr in github_data.pull_requests:
        if pr.author_email and pr.author_email not in all_authors:
            all_authors[pr.author_email] = pr.author_name

    if contributor:
        if contributor not in all_authors:
            console.print(f"[yellow]Warning:[/yellow] contributor {contributor!r} not found in collected data.")
            return
        authors = {contributor: all_authors[contributor]}
    else:
        authors = all_authors

    console.print(f"\nGenerating reports for [bold]{len(authors)}[/bold] contributor(s)...\n")

    for email, name in authors.items():
        console.print(f"  [cyan]{name}[/cyan] ({email})")

        code = code_quality_agg.aggregate(github_data, email)
        mult = multiplier_agg.aggregate(github_data, email)
        rel = reliability_agg.aggregate(github_data, email)
        author_attribution = attr_map.get(email, {})

        summary, highlights = narrative.generate(
            author_name=name,
            period_from=from_date,
            period_to=to_date,
            code=code,
            multiplier=mult,
            reliability=rel,
            attribution=author_attribution,
            api_key=cfg.anthropic.api_key,
            model=cfg.anthropic.model,
        )

        out_path = report.generate(
            author_name=name,
            author_email=email,
            period_from=from_date,
            period_to=to_date,
            generated_on=generated_on,
            summary=summary,
            highlights=highlights,
            code=code,
            multiplier=mult,
            reliability=rel,
            attribution=author_attribution,
            datadog_data=datadog_data,
            output_dir=output_dir,
        )

        console.print(f"    → [green]{out_path}[/green]")

    console.print("\n[bold green]Done.[/bold green]")


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    cli()
