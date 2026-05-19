from datetime import datetime
from typing import Protocol

from signals import ProviderOutput


class Provider(Protocol):
    name: str

    def collect(self, since: datetime, until: datetime) -> ProviderOutput: ...
