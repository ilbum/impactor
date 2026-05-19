from pathlib import Path

from aggregators.code_quality import CodeQualityStats
from aggregators.multiplier import MultiplierStats
from aggregators.reliability import ReliabilityStats
from collectors.datadog import DatadogData


def generate(
    author_name: str,
    author_email: str,
    period_from: str,
    period_to: str,
    generated_on: str,
    summary: str,
    highlights: list[str],
    code: CodeQualityStats,
    multiplier: MultiplierStats,
    reliability: ReliabilityStats,
    attribution: dict[str, float],
    datadog_data: DatadogData,
    output_dir: str,
) -> Path:
    slug = author_name.lower().replace(" ", "_")
    filename = f"{slug}_{period_from}_{period_to}.md"
    path = Path(output_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    lines += [
        f"# Contribution Report: {author_name}",
        f"**Period:** {period_from} → {period_to}  ",
        f"**Generated:** {generated_on}",
        "",
        "---",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Impact Highlights",
        "",
    ]
    for h in highlights:
        lines.append(f"- {h}")
    lines += ["", "---", "", "## Signal Breakdown", ""]

    # Outcome metrics
    lines += ["### Outcome Metrics (Datadog)", ""]
    attributed_metrics = {m.name for m in datadog_data.metrics if m.is_improvement}
    if attribution:
        lines += [
            "| Metric | Change | Direction | Attribution |",
            "|--------|--------|-----------|-------------|",
        ]
        for metric_name, credit in attribution.items():
            metric = next((m for m in datadog_data.metrics if m.name == metric_name), None)
            if metric is None:
                continue
            delta_str = f"{metric.delta:+.2f}" if metric.delta is not None else "n/a"
            arrow = "↓" if metric.direction == "down" else "↑"
            pct = round(credit * 100)
            lines.append(f"| `{metric_name}` | {delta_str} | {arrow} | {pct}% attributed share |")
    else:
        lines.append("_No improved Datadog metrics attributed to this contributor in this period._")
    lines.append("")

    # Code authorship
    lines += [
        "### Code Authorship",
        "",
        f"- **Commits:** {code.commit_count} | **PRs merged:** {code.prs_merged}",
        f"- **Features:** {code.feature_prs} | **Bug fixes:** {code.bug_fix_prs}",
        f"- **PRs touching tests:** {code.test_prs}",
        "",
    ]

    # Multiplier effect
    lines += [
        "### Multiplier Effect",
        "",
        f"- **PRs reviewed:** {multiplier.prs_reviewed}",
        f"- **Approvals given (unblocking):** {multiplier.approvals_given}",
        f"- **Documentation PRs:** {multiplier.documentation_prs}",
        "",
    ]

    # Reliability context
    lines += ["### Reliability Context", ""]
    if reliability.reverted_commits:
        lines.append(f"- **Reverted commits:** {len(reliability.reverted_commits)}")
        for r in reliability.reverted_commits:
            date_str = r.timestamp.strftime("%Y-%m-%d")
            lines.append(f"  - `{r.sha[:7]}` — {date_str}: _{r.message}_")
    else:
        lines.append("- **Reverted commits:** 0")
    lines += ["", "---", "", "## Manager Notes", ""]
    lines.append("> *(Fill this in before sharing with the contributor)*")
    lines.append("")

    path.write_text("\n".join(lines))
    return path
