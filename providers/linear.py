from datetime import datetime

from signals import ProviderOutput


class LinearProvider:
    name = "linear"

    def __init__(self, api_key: str, team_ids: list[str]) -> None:
        self._api_key = api_key
        self._team_ids = team_ids

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        raise NotImplementedError(
            "Linear provider is not yet implemented. "
            "Remove [providers.linear] from your config to skip it."
        )
