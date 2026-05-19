from collections import defaultdict

from collectors.datadog import DatadogData, MetricSeries
from collectors.github import GitHubData


# author_email -> metric_name -> credit fraction (0.0–1.0)
AttributionMap = dict[str, dict[str, float]]


def build(
    github_data: GitHubData,
    datadog_data: DatadogData,
    service_map: dict[str, str],
) -> AttributionMap:
    attribution: AttributionMap = defaultdict(lambda: defaultdict(float))

    improved_metrics = [m for m in datadog_data.metrics if m.is_improvement and m.service_tag]

    for metric in improved_metrics:
        path_prefix = service_map.get(metric.service_tag)
        if path_prefix is None:
            continue

        author_commit_counts = _count_commits_by_author(github_data, path_prefix)
        total = sum(author_commit_counts.values())
        if total == 0:
            continue

        for author_email, count in author_commit_counts.items():
            attribution[author_email][metric.name] = count / total

    return dict(attribution)


def _count_commits_by_author(github_data: GitHubData, path_prefix: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for commit in github_data.commits:
        if any(f.startswith(path_prefix) for f in commit.files):
            counts[commit.author_email] += 1
    return counts
