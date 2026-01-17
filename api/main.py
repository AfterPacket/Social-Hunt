from __future__ import annotations

import asyncio
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from social_hunt.registry import build_registry, list_provider_names
from social_hunt.engine import SocialHuntEngine
from api.settings_store import SettingsStore, mask_for_client

app = FastAPI(title="Social-Hunt API", version="2.1.0")

# ---- auth (simple admin token) ----
ADMIN_TOKEN = (os.getenv("SOCIAL_HUNT_PLUGIN_TOKEN") or "").strip()


def require_admin(x_plugin_token: Optional[str]) -> None:
    # Admin token is server-side only (set via env var). The dashboard "Token" page
    # merely stores the token in your browser and sends it with requests.
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Server missing SOCIAL_HUNT_PLUGIN_TOKEN (set env var and restart the API)",
        )
    if not x_plugin_token or x_plugin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---- settings store ----
SETTINGS_PATH = os.getenv("SOCIAL_HUNT_SETTINGS_PATH", "data/settings.json")
settings_store = SettingsStore(SETTINGS_PATH)


# ---- core engine ----
registry = build_registry("providers.yaml")
engine = SocialHuntEngine(registry, max_concurrency=6)


def reload_registry() -> None:
    global registry
    registry = build_registry("providers.yaml")
    engine.registry = registry


# ---- simple in-memory job store (swap to Redis for production) ----
JOBS: Dict[str, Dict[str, Any]] = {}


class SearchRequest(BaseModel):
    username: str
    providers: Optional[List[str]] = None


@app.get("/api/providers")
async def api_providers():
    return {"providers": list_provider_names(registry)}


@app.post("/api/providers/reload")
async def api_providers_reload(x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token")):
    require_admin(x_plugin_token)
    reload_registry()
    return {"ok": True, "providers": list_provider_names(registry)}


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


# ---------------------------
# Reverse image search links
# ---------------------------

def _build_reverse_links(image_url: str) -> List[Dict[str, str]]:
    from urllib.parse import quote_plus

    u = image_url.strip()
    q = quote_plus(u)

    # Note: some endpoints change over time; these are common URL-entry points.
    return [
        {"name": "Google Images", "url": f"https://www.google.com/searchbyimage?image_url={q}"},
        {"name": "Google Lens", "url": f"https://lens.google.com/uploadbyurl?url={q}"},
        {"name": "TinEye", "url": f"https://tineye.com/search?url={q}"},
        {"name": "Bing Visual Search", "url": f"https://www.bing.com/images/search?q=imgurl:{q}&view=detailv2&iss=sbi"},
        {"name": "Yandex Images", "url": f"https://yandex.com/images/search?rpt=imageview&url={q}"},
    ]


class ReverseImageReq(BaseModel):
    image_url: str


@app.post("/api/reverse_image_links")
async def api_reverse_image_links(req: ReverseImageReq):
    image_url = (req.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url required")
    if not re.match(r"^https?://", image_url, re.I):
        raise HTTPException(status_code=400, detail="image_url must be http(s)")
    return {"links": _build_reverse_links(image_url)}


# ---------------------------
# Settings (dynamic)
# ---------------------------


@app.get("/api/settings")
async def api_get_settings(x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token")):
    require_admin(x_plugin_token)
    data = settings_store.load()
    return {"settings": mask_for_client(data)}


class SettingsPutReq(BaseModel):
    settings: Dict[str, Any]


@app.put("/api/settings")
async def api_put_settings(req: SettingsPutReq, x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token")):
    require_admin(x_plugin_token)

    if not isinstance(req.settings, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")

    current = settings_store.load()
    for k, v in req.settings.items():
        # allow clearing by empty string
        current[str(k)] = v

    settings_store.save(current)
    return {"ok": True}


# ---------------------------
# Plugin uploads (YAML packs)
# ---------------------------


PLUGIN_DIR = Path("plugins/providers")
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(name: str) -> str:
    # keep simple
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return base or "plugin"


def _install_yaml_bytes(filename: str, data: bytes) -> str:
    out_name = _safe_name(Path(filename).name)
    if not (out_name.endswith(".yaml") or out_name.endswith(".yml")):
        out_name += ".yaml"
    out_path = PLUGIN_DIR / out_name
    out_path.write_bytes(data)
    return str(out_path)


def _extract_yaml_from_zip(zbytes: bytes) -> List[str]:
    installed: List[str] = []
    with zipfile.ZipFile(BytesIO(zbytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            # block traversal
            if name.startswith("/") or ".." in name:
                continue
            lower = name.lower()
            if not (lower.endswith(".yaml") or lower.endswith(".yml")):
                continue
            data = z.read(info)
            installed.append(_install_yaml_bytes(Path(name).name, data))
    return installed


@app.post("/api/plugin/upload")
async def api_plugin_upload(
    file: UploadFile = File(...),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    fname = (file.filename or "plugin").strip()
    lower = fname.lower()

    installed: List[str] = []

    # Limit upload size ~2MB
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="upload too large")

    if lower.endswith(".zip"):
        installed = _extract_yaml_from_zip(raw)
    elif lower.endswith(".yaml") or lower.endswith(".yml"):
        installed = [_install_yaml_bytes(fname, raw)]
    else:
        raise HTTPException(status_code=400, detail="upload must be .yaml/.yml or .zip")

    reload_registry()

    return {"ok": True, "installed": installed, "providers": list_provider_names(registry)}


# ---- UI ----
app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
async def root():
    return FileResponse("web/index.html")
