from __future__ import annotations

import csv
import json
from datetime import datetime
from typing import List

from .types import ProviderResult


def export_results(results: List[ProviderResult], fmt: str = "csv") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = (fmt or "csv").lower().strip()

    if fmt == "json":
        filename = f"social_hunt_{ts}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)
        return filename

    filename = f"social_hunt_{ts}.csv"
    fieldnames = [
        "provider",
        "username",
        "url",
        "status",
        "http_status",
        "elapsed_ms",
        "display_name",
        "avatar_url",
        "followers",
        "following",
        "subscribers",
        "created_at",
        "bio_domains",
        "bio_urls",
        "avatar_sha256",
        "avatar_dhash",
        "avatar_cluster_id",
        "timestamp_iso",
        "error",
    ]

    with open(filename, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            d = r.to_dict()
            profile = (d.get("profile") or {})
            row = {k: d.get(k) for k in fieldnames}
            # Flatten common profile keys for CSV convenience
            row["display_name"] = profile.get("display_name")
            row["avatar_url"] = profile.get("avatar_url")
            row["followers"] = profile.get("followers")
            row["following"] = profile.get("following")
            row["subscribers"] = profile.get("subscribers")
            row["created_at"] = profile.get("created_at")
            # New optional addon fields (flattened)
            bd = profile.get("bio_domains")
            bu = profile.get("bio_urls")
            row["bio_domains"] = ",".join(bd) if isinstance(bd, list) else (bd or "")
            row["bio_urls"] = ",".join(bu) if isinstance(bu, list) else (bu or "")
            row["avatar_sha256"] = profile.get("avatar_sha256")
            row["avatar_dhash"] = profile.get("avatar_dhash")
            row["avatar_cluster_id"] = profile.get("avatar_cluster_id")
            w.writerow(row)

    return filename
