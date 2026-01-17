from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from social_hunt.registry import build_registry, list_provider_names
from social_hunt.engine import SocialHuntEngine

app = FastAPI(title="Social-Hunt API", version="2.0.0")

# ---- core engine ----
registry = build_registry("providers.yaml")
engine = SocialHuntEngine(registry, max_concurrency=6)

# ---- simple in-memory job store (swap to Redis for production) ----
JOBS: Dict[str, Dict[str, Any]] = {}

class SearchRequest(BaseModel):
    username: str
    providers: Optional[List[str]] = None

@app.get("/api/providers")
async def api_providers():
    return {"providers": list_provider_names(registry)}

@app.get("/api/whoami")
async def api_whoami(request: Request):
    """Return best-effort client IP as seen by the API (helps verify proxy headers)."""
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    xri = (request.headers.get("x-real-ip") or "").strip()
    client_host = request.client.host if request.client else ""

    # X-Forwarded-For can be a comma-separated list; the left-most is the original client.
    ip = ""
    if xff:
        ip = xff.split(",")[0].strip()
    elif xri:
        ip = xri
    else:
        ip = client_host

    return {
        "client_ip": ip,
        "via": "x-forwarded-for" if xff else ("x-real-ip" if xri else "socket"),
        "user_agent": request.headers.get("user-agent", ""),
    }

@app.post("/api/search")
async def api_search(req: SearchRequest):
    username = (req.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    # basic sanity cap (avoid accidental huge input)
    if len(username) > 64:
        raise HTTPException(status_code=400, detail="username too long")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"state": "running", "results": [], "username": username}

    async def runner():
        try:
            res = await engine.scan_username(username, req.providers)
            JOBS[job_id]["results"] = [r.to_dict() for r in res]
            JOBS[job_id]["state"] = "done"
        except Exception as e:
            JOBS[job_id]["state"] = "failed"
            JOBS[job_id]["error"] = str(e)

    asyncio.create_task(runner())
    return {"job_id": job_id}

@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job

# ---- UI ----
app.mount("/static", StaticFiles(directory="web"), name="static")

@app.get("/")
async def root():
    return FileResponse("web/index.html")
