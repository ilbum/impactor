from datetime import datetime

from signals import ProviderOutput


class PagerDutyProvider:
    name = "pagerduty"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        raise NotImplementedError(
            "PagerDuty provider is not yet implemented. "
            "Remove [providers.pagerduty] from your config to skip it."
        )
