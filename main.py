from datetime import datetime, timezone

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

import attribution as attribution_engine
import config as config_loader
import narrative
import report
from signals import CodeActivitySignal, CollaborationSignal, OutcomeMetric, ProviderOutput, ReliabilitySignal

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
    providers = config_loader.load_providers(cfg)
    output_dir = output or cfg.output.path

    since = _parse_date(from_date)
    until = _parse_date(to_date)
    generated_on = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    outputs: list[ProviderOutput] = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for provider in providers:
            task = progress.add_task(f"Collecting from {provider.name}...", total=None)
            result = provider.collect(since, until)
            outputs.append(result)
            summary = _summarize(result)
            progress.update(task, description=f"{provider.name}: {summary}")

        task = progress.add_task("Building attribution map...", total=None)
        attr_map = attribution_engine.build(outputs, cfg.service_map)
        progress.update(task, description="Attribution complete")

    # Collect all authors seen across code_activity signals
    authors: dict[str, str] = {}  # email -> name
    for o in outputs:
        for s in o.code_activity:
            if s.author_email and s.author_email not in authors:
                authors[s.author_email] = s.author_name

    if contributor:
        if contributor not in authors:
            console.print(f"[yellow]Warning:[/yellow] {contributor!r} not found in collected data.")
            return
        authors = {contributor: authors[contributor]}

    all_outcome_metrics: list[OutcomeMetric] = [m for o in outputs for m in o.outcome_metrics]

    console.print(f"\nGenerating reports for [bold]{len(authors)}[/bold] contributor(s)...\n")

    for email, name in authors.items():
        console.print(f"  [cyan]{name}[/cyan] ({email})")

        code = _find_code(outputs, email)
        collab = _find_collab(outputs, email)
        rel = _find_reliability(outputs, email)
        author_attribution = attr_map.get(email, {})

        summary, highlights = narrative.generate(
            author_name=name,
            period_from=from_date,
            period_to=to_date,
            code=code,
            collab=collab,
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
            collab=collab,
            reliability=rel,
            attribution=author_attribution,
            outcome_metrics=all_outcome_metrics,
            output_dir=output_dir,
        )

        console.print(f"    → [green]{out_path}[/green]")

    console.print("\n[bold green]Done.[/bold green]")


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _summarize(output: ProviderOutput) -> str:
    parts = []
    if output.outcome_metrics:
        parts.append(f"{len(output.outcome_metrics)} metrics")
    if output.code_activity:
        total = sum(s.commit_count for s in output.code_activity)
        parts.append(f"{total} commits")
    if output.collaboration:
        parts.append(f"{len(output.collaboration)} reviewers")
    return ", ".join(parts) if parts else "no data"


def _find_code(outputs: list[ProviderOutput], email: str) -> CodeActivitySignal | None:
    return next((s for o in outputs for s in o.code_activity if s.author_email == email), None)


def _find_collab(outputs: list[ProviderOutput], email: str) -> CollaborationSignal | None:
    return next((s for o in outputs for s in o.collaboration if s.author_email == email), None)


def _find_reliability(outputs: list[ProviderOutput], email: str) -> ReliabilitySignal | None:
    return next((s for o in outputs for s in o.reliability if s.author_email == email), None)


if __name__ == "__main__":
    cli()
