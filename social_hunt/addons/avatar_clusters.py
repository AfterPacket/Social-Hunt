from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import httpx

from ..addons_base import BaseAddon
from ..rate_limit import HostRateLimiter
from ..types import ProviderResult


def _hex_to_int(h: str) -> Optional[int]:
    try:
        return int(h, 16)
    except Exception:
        return None


def _hamming_64(a: str, b: str) -> Optional[int]:
    ia = _hex_to_int(a)
    ib = _hex_to_int(b)
    if ia is None or ib is None:
        return None
    return (ia ^ ib).bit_count()


@dataclass
class _Item:
    idx: int
    provider: str
    sha: str
    dhash: str


class AvatarClustersAddon(BaseAddon):
    """Cluster providers by matching avatar fingerprints.

    1) Exact sha256 matches
    2) Near-match dHash (within a small Hamming distance)
    """

    name = "avatar_clusters"

    def __init__(self, *, dhash_max_distance: int = 4) -> None:
        self.dhash_max_distance = int(dhash_max_distance)

    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: HostRateLimiter | None = None,
    ) -> None:
        items: List[_Item] = []
        for i, r in enumerate(results):
            prof = r.profile or {}
            sha = prof.get("avatar_sha256")
            dh = prof.get("avatar_dhash")
            if isinstance(sha, str) and isinstance(dh, str) and sha and dh:
                items.append(_Item(i, r.provider, sha, dh))

        if len(items) < 2:
            return

        # Exact clusters by sha256
        sha_groups: Dict[str, List[_Item]] = {}
        for it in items:
            sha_groups.setdefault(it.sha, []).append(it)

        clusters: List[Tuple[str, List[_Item], str]] = []
        used = set()
        cluster_no = 1

        for sha, group in sha_groups.items():
            if len(group) >= 2:
                cid = f"cluster-{cluster_no}"
                cluster_no += 1
                clusters.append((cid, group, "sha256"))
                for g in group:
                    used.add(g.idx)

        # Near-match clusters by dHash, only among items not already in a sha256 cluster.
        remaining = [it for it in items if it.idx not in used]
        # Simple O(n^2) since result set is small.
        visited = set()
        for i in range(len(remaining)):
            if remaining[i].idx in visited:
                continue
            base = remaining[i]
            group = [base]
            for j in range(i + 1, len(remaining)):
                other = remaining[j]
                if other.idx in visited:
                    continue
                dist = _hamming_64(base.dhash, other.dhash)
                if dist is not None and dist <= self.dhash_max_distance:
                    group.append(other)
            if len(group) >= 2:
                cid = f"cluster-{cluster_no}"
                cluster_no += 1
                clusters.append((cid, group, f"dhash<= {self.dhash_max_distance}"))
                for g in group:
                    visited.add(g.idx)

        if not clusters:
            return

        # Attach cluster info to each profile
        for cid, group, method in clusters:
            provs = [g.provider for g in group]
            for g in group:
                prof = results[g.idx].profile or {}
                prof["avatar_cluster_id"] = cid
                prof["avatar_cluster_method"] = method
                prof["avatar_cluster_providers"] = provs
                results[g.idx].profile = prof


ADDONS = [AvatarClustersAddon()]
