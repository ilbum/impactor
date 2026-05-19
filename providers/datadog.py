import re
from datetime import datetime

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.dashboards_api import DashboardsApi
from datadog_api_client.v1.api.metrics_api import MetricsApi

from signals import OutcomeMetric, ProviderOutput

_LOWER_IS_BETTER = ("error", "latency", "p50", "p95", "p99", "duration", "timeout")


class DatadogProvider:
    name = "datadog"

    def __init__(self, api_key: str, app_key: str, dashboards: list[str]) -> None:
        self._api_key = api_key
        self._app_key = app_key
        self._dashboards = dashboards

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        config = Configuration()
        config.api_key["apiKeyAuth"] = self._api_key
        config.api_key["appKeyAuth"] = self._app_key

        with ApiClient(config) as client:
            metric_names = _metric_names_from_dashboards(client, self._dashboards)
            metrics = _query_metrics(client, metric_names, since, until)

        return ProviderOutput(outcome_metrics=metrics)


def _metric_names_from_dashboards(client: ApiClient, dashboard_ids: list[str]) -> list[str]:
    api = DashboardsApi(client)
    names: set[str] = set()

    for dash_id in dashboard_ids:
        try:
            dashboard = api.get_dashboard(dash_id)
            for widget in dashboard.widgets or []:
                _extract_from_widget(widget, names)
        except Exception as e:
            print(f"Warning: could not fetch dashboard {dash_id}: {e}")

    return list(names)


def _extract_from_widget(widget, names: set[str]) -> None:
    definition = getattr(widget, "definition", None)
    if definition is None:
        return
    nested = getattr(definition, "widgets", None)
    if nested:
        for w in nested:
            _extract_from_widget(w, names)
        return
    requests = getattr(definition, "requests", None)
    if not requests:
        return
    items = requests if isinstance(requests, list) else requests.values()
    for req in items:
        query = getattr(req, "q", None) or getattr(req, "query", None)
        if query and isinstance(query, str):
            match = re.search(r"[\w.]+", query)
            if match:
                names.add(match.group(0))


def _query_metrics(
    client: ApiClient,
    metric_names: list[str],
    since: datetime,
    until: datetime,
) -> list[OutcomeMetric]:
    api = MetricsApi(client)
    results: list[OutcomeMetric] = []
    start_ts = int(since.timestamp())
    end_ts = int(until.timestamp())

    for name in metric_names:
        try:
            resp = api.query_metrics(_from=start_ts, to=end_ts, query=name)
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
                lower_is_better = any(kw in name for kw in _LOWER_IS_BETTER)
                is_improvement = (delta < 0) if lower_is_better else (delta > 0)
                service_tag = _extract_service_tag(series)

                results.append(OutcomeMetric(
                    name=name,
                    source="datadog",
                    service_tag=service_tag,
                    delta=delta,
                    is_improvement=is_improvement,
                    direction="down" if delta < 0 else "up",
                ))
        except Exception as e:
            print(f"Warning: could not query metric {name}: {e}")

    return results


def _extract_service_tag(series) -> str | None:
    for tag in getattr(series, "tag_set", None) or []:
        if tag.startswith("service:"):
            return tag.split(":", 1)[1]
    return None
