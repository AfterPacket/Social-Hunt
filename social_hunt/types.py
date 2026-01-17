from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional, Dict

class ResultStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    ERROR = "error"

@dataclass
class ProviderResult:
    provider: str
    username: str
    url: str
    status: ResultStatus
    http_status: Optional[int] = None
    elapsed_ms: int = 0
    evidence: Dict[str, Any] = None
    profile: Dict[str, Any] = None
    error: Optional[str] = None
    timestamp_iso: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        if self.evidence is None:
            d["evidence"] = {}
        if self.profile is None:
            d["profile"] = {}
        return d
