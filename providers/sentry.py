from datetime import datetime

from signals import ProviderOutput


class SentryProvider:
    name = "sentry"

    def __init__(self, auth_token: str, org_slug: str) -> None:
        self._auth_token = auth_token
        self._org_slug = org_slug

    def collect(self, since: datetime, until: datetime) -> ProviderOutput:
        raise NotImplementedError(
            "Sentry provider is not yet implemented. "
            "Remove [providers.sentry] from your config to skip it."
        )
