from dataclasses import dataclass, field
from datetime import datetime

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.dashboards_api import DashboardsApi
from datadog_api_client.v1.api.metrics_api import MetricsApi


@dataclass
class MetricSeries:
    name: str
    service_tag: str | None
    start_value: float | None
    end_value: float | None
    delta: float | None
    is_improvement: bool  # True if lower is better and delta < 0, or higher is better and delta > 0
    direction: str        # "up" or "down"
    unit: str | None = None


@dataclass
class DatadogData:
    metrics: list[MetricSeries] = field(default_factory=list)


def collect(
    api_key: str,
    app_key: str,
    dashboard_ids: list[str],
    since: datetime,
    until: datetime,
) -> DatadogData:
    config = Configuration()
    config.api_key["apiKeyAuth"] = api_key
    config.api_key["appKeyAuth"] = app_key

    data = DatadogData()

    with ApiClient(config) as client:
        metric_names = _metric_names_from_dashboards(client, dashboard_ids)
        data.metrics = _query_metrics(client, metric_names, since, until)

    return data


def _metric_names_from_dashboards(client: ApiClient, dashboard_ids: list[str]) -> list[str]:
    api = DashboardsApi(client)
    metric_names: set[str] = set()

    for dash_id in dashboard_ids:
        try:
            dashboard = api.get_dashboard(dash_id)
            for widget in dashboard.widgets or []:
                _extract_metrics_from_widget(widget, metric_names)
        except Exception as e:
            print(f"Warning: could not fetch dashboard {dash_id}: {e}")

    return list(metric_names)


def _extract_metrics_from_widget(widget, metric_names: set[str]) -> None:
    definition = getattr(widget, "definition", None)
    if definition is None:
        return

    # Handle group widgets that contain nested widgets
    nested = getattr(definition, "widgets", None)
    if nested:
        for w in nested:
            _extract_metrics_from_widget(w, metric_names)
        return

    requests = getattr(definition, "requests", None)
    if not requests:
        return

    items = requests if isinstance(requests, list) else requests.values()
    for req in items:
        query = getattr(req, "q", None) or getattr(req, "query", None)
        if query and isinstance(query, str):
            # Extract bare metric name (everything before { or first space)
            import re
            match = re.search(r"[\w.]+", query)
            if match:
                metric_names.add(match.group(0))


def _query_metrics(
    client: ApiClient,
    metric_names: list[str],
    since: datetime,
    until: datetime,
) -> list[MetricSeries]:
    api = MetricsApi(client)
    results: list[MetricSeries] = []

    start_ts = int(since.timestamp())
    end_ts = int(until.timestamp())

    for name in metric_names:
        try:
            resp = api.query_metrics(
                _from=start_ts,
                to=end_ts,
                query=name,
            )
            if not resp.series:
                continue

            for series in resp.series:
                pointlist = series.pointlist or []
                if len(pointlist) < 2:
                    continue

                start_val = pointlist[0][1]
                end_val = pointlist[-1][1]

                if start_val is None or end_val is None:
                    continue

                delta = end_val - start_val
                # Heuristic: for error/latency metrics lower is better; for throughput higher is better
                lower_is_better = any(kw in name for kw in ("error", "latency", "p50", "p95", "p99", "duration", "timeout"))
                is_improvement = (delta < 0) if lower_is_better else (delta > 0)

                service_tag = _extract_service_tag(series)

                results.append(MetricSeries(
                    name=name,
                    service_tag=service_tag,
                    start_value=start_val,
                    end_value=end_val,
                    delta=delta,
                    is_improvement=is_improvement,
                    direction="down" if delta < 0 else "up",
                ))
        except Exception as e:
            print(f"Warning: could not query metric {name}: {e}")

    return results


def _extract_service_tag(series) -> str | None:
    tag_set = getattr(series, "tag_set", None) or []
    for tag in tag_set:
        if tag.startswith("service:"):
            return tag.split(":", 1)[1]
    return None
