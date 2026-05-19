from pathlib import Path

from signals import CodeActivitySignal, CollaborationSignal, OutcomeMetric, ReliabilitySignal


def generate(
    author_name: str,
    author_email: str,
    period_from: str,
    period_to: str,
    generated_on: str,
    summary: str | None,
    highlights: list[str] | None,
    code: CodeActivitySignal | None,
    collab: CollaborationSignal | None,
    reliability: ReliabilitySignal | None,
    attribution: dict[str, float],
    outcome_metrics: list[OutcomeMetric],
    output_dir: str,
) -> Path:
    slug = author_name.lower().replace(" ", "_")
    path = Path(output_dir) / f"{slug}_{period_from}_{period_to}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        f"# Contribution Report: {author_name}",
        f"**Period:** {period_from} → {period_to}  ",
        f"**Generated:** {generated_on}",
        "",
        "---",
        "",
    ]

    if summary:
        lines += ["## Summary", "", summary, ""]
    if highlights:
        lines += ["## Impact Highlights", "", *[f"- {h}" for h in highlights], ""]

    lines += ["---", "", "## Signal Breakdown", ""]

    # Outcome metrics — only if attribution exists
    if attribution and outcome_metrics:
        attributed_names = set(attribution.keys())
        attributed = [m for m in outcome_metrics if m.name in attributed_names and m.is_improvement]
        if attributed:
            lines += [
                "### Outcome Metrics",
                "",
                "| Metric | Source | Change | Direction | Attribution |",
                "|--------|--------|--------|-----------|-------------|",
            ]
            for m in attributed:
                delta_str = f"{m.delta:+.2f}" if m.delta is not None else "n/a"
                arrow = "↓" if m.direction == "down" else "↑"
                pct = round(attribution[m.name] * 100)
                lines.append(f"| `{m.name}` | {m.source} | {delta_str} | {arrow} | {pct}% |")
            lines.append("")
    elif "git_ownership" in attribution:
        pct = round(attribution["git_ownership"] * 100)
        lines += [
            "### Ownership Share",
            "",
            f"_{pct}% of total commits in period (no outcome metrics provider connected)_",
            "",
        ]

    # Code authorship — only if present
    if code:
        lines += [
            "### Code Authorship",
            "",
            f"- **Commits:** {code.commit_count} | **PRs merged:** {code.prs_merged}",
            f"- **Features:** {code.feature_prs} | **Bug fixes:** {code.bug_fix_prs}",
            f"- **PRs touching tests:** {code.test_prs}",
            "",
        ]

    # Collaboration — only if present
    if collab:
        lines += [
            "### Multiplier Effect",
            "",
            f"- **PRs reviewed:** {collab.prs_reviewed}",
            f"- **Approvals given (unblocking):** {collab.approvals_given}",
            f"- **Documentation PRs:** {collab.documentation_prs}",
            "",
        ]

    # Reliability — only if reverts or incidents exist
    if reliability and (reliability.reverted_commits or reliability.incidents):
        lines += ["### Reliability Context", ""]
        if reliability.reverted_commits:
            lines.append(f"- **Reverted commits:** {len(reliability.reverted_commits)}")
            for r in reliability.reverted_commits:
                date_str = r.timestamp.strftime("%Y-%m-%d")
                lines.append(f"  - `{r.sha[:7]}` — {date_str}: _{r.message}_")
        if reliability.incidents:
            lines.append(f"- **Incidents attributed:** {len(reliability.incidents)}")
            for i in reliability.incidents:
                date_str = i.timestamp.strftime("%Y-%m-%d")
                lines.append(f"  - [{i.id}] {date_str}: _{i.title}_ (via {i.source})")
        lines.append("")

    lines += ["---", "", "## Manager Notes", "", "> *(Fill this in before sharing with the contributor)*", ""]

    path.write_text("\n".join(lines))
    return path
