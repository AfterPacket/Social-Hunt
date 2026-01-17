from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any

from .types import ProviderResult

class BaseProvider(ABC):
    name: str = "base"
    timeout: int = 10
    ua_profile: str = "desktop_chrome"

    @abstractmethod
    def build_url(self, username: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def check(self, username: str, client, headers: Dict[str, str]) -> ProviderResult:
        raise NotImplementedError

    def meta(self) -> Dict[str, Any]:
        return {"name": self.name, "timeout": self.timeout, "ua_profile": self.ua_profile}
