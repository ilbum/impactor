from collections import defaultdict

from signals import ProviderOutput

# author_email -> metric_name -> credit fraction (0.0–1.0)
AttributionMap = dict[str, dict[str, float]]


def build(outputs: list[ProviderOutput], service_map: dict[str, str]) -> AttributionMap:
    improved = [m for o in outputs for m in o.outcome_metrics if m.is_improvement and m.service_tag]

    if improved:
        return _metric_based(outputs, improved, service_map)

    return _git_ownership(outputs)


def _metric_based(
    outputs: list[ProviderOutput],
    improved_metrics,
    service_map: dict[str, str],
) -> AttributionMap:
    attribution: AttributionMap = defaultdict(lambda: defaultdict(float))

    all_commits = [c for o in outputs for s in o.code_activity for c in s.commits]

    for metric in improved_metrics:
        path_prefix = service_map.get(metric.service_tag)
        if path_prefix is None:
            continue

        counts: dict[str, int] = defaultdict(int)
        for commit in all_commits:
            if any(f.startswith(path_prefix) for f in commit.files):
                counts[commit.author_email] += 1

        total = sum(counts.values())
        if total == 0:
            continue

        for email, count in counts.items():
            attribution[email][metric.name] = count / total

    return dict(attribution)


def _git_ownership(outputs: list[ProviderOutput]) -> AttributionMap:
    total_commits = sum(s.commit_count for o in outputs for s in o.code_activity)
    if total_commits == 0:
        return {}

    return {
        s.author_email: {"git_ownership": s.commit_count / total_commits}
        for o in outputs
        for s in o.code_activity
        if s.commit_count > 0
    }
