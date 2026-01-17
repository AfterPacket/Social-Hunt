from __future__ import annotations

import asyncio
import hashlib
import io
import os
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import httpx
from PIL import Image

from social_hunt.registry import build_registry, list_provider_names
from social_hunt.engine import SocialHuntEngine
from social_hunt.addons_registry import build_addon_registry, load_enabled_addons, list_addon_names
from social_hunt.addons.net_safety import safe_fetch_bytes, UnsafeURLError
from social_hunt.plugin_loader import plugins_dir, list_installed_plugins

app = FastAPI(title="Social-Hunt API", version="2.1.0")

# --- anti-cache headers (helps when deployed behind proxies/CDNs) ---
@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path or ""
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ---- core engine ----
registry = build_registry("providers.yaml")
addons_registry = build_addon_registry()
enabled_addons = load_enabled_addons("addons.yaml")
engine = SocialHuntEngine(
    registry,
    addons=addons_registry,
    enabled_addons=enabled_addons,
    max_concurrency=6,
)

# ---- simple in-memory job store (swap to Redis for production) ----
JOBS: Dict[str, Dict[str, Any]] = {}

# ---- plugin upload / reload ----
RELOAD_LOCK = asyncio.Lock()


def _admin_token() -> str:
    return (os.getenv("SOCIAL_HUNT_PLUGIN_TOKEN", "") or "").strip()


def _web_plugin_upload_enabled() -> bool:
    return (os.getenv("SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD", "") or "").strip() == "1"


def _allow_py_plugins() -> bool:
    # same flag used by registry/addons_registry
    return (os.getenv("SOCIAL_HUNT_ALLOW_PY_PLUGINS", "") or "").strip() == "1"


def _require_admin(request: Request) -> None:
    if not _web_plugin_upload_enabled():
        raise HTTPException(status_code=403, detail="web plugin upload is disabled")
    token = _admin_token()
    if not token:
        raise HTTPException(status_code=403, detail="SOCIAL_HUNT_PLUGIN_TOKEN not set")
    supplied = (request.headers.get("x-plugin-token") or "").strip()
    if not supplied or supplied != token:
        raise HTTPException(status_code=403, detail="invalid plugin token")


def _ensure_plugin_dirs() -> Path:
    root = plugins_dir()
    (root / "providers").mkdir(parents=True, exist_ok=True)
    (root / "python" / "providers").mkdir(parents=True, exist_ok=True)
    (root / "python" / "addons").mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(name: str) -> str:
    # keep it simple, filesystem-safe
    base = "".join(c for c in name if c.isalnum() or c in ("-", "_", "."))
    base = base.strip("._-")
    return base or "plugin"


async def _reload_engine() -> Dict[str, Any]:
    """Reload providers + addons from disk (including plugins) without restart."""
    async with RELOAD_LOCK:
        global registry, addons_registry, enabled_addons, engine
        registry = build_registry("providers.yaml")
        addons_registry = build_addon_registry()
        enabled_addons = load_enabled_addons("addons.yaml")
        engine.registry = registry
        engine.addons = addons_registry
        engine.enabled_addons = enabled_addons
        return {
            "providers": list_provider_names(registry),
            "addons_available": list_addon_names(addons_registry),
            "addons_enabled": enabled_addons,
        }

class SearchRequest(BaseModel):
    username: str
    providers: Optional[List[str]] = None


class ReverseImageRequest(BaseModel):
    job_id: str
    image_url: str


class ReverseImageLinksRequest(BaseModel):
    image_url: str


@app.get("/api/addons")
async def api_addons():
    """List available addons and which ones are enabled."""
    return {
        "available": list_addon_names(addons_registry),
        "enabled": enabled_addons,
    }


@app.get("/api/plugins")
async def api_plugins():
    """List plugin files present on disk.

    Note: python plugins are only loaded if SOCIAL_HUNT_ALLOW_PY_PLUGINS=1.
    Web upload/reload endpoints require SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1
    and a matching X-Plugin-Token.
    """
    inv = list_installed_plugins()
    inv["web_upload_enabled"] = _web_plugin_upload_enabled()
    inv["python_plugins_allowed"] = _allow_py_plugins()
    return inv


@app.post("/api/plugins/reload")
async def api_plugins_reload(request: Request):
    _require_admin(request)
    return await _reload_engine()


@app.post("/api/plugins/upload")
async def api_plugins_upload(request: Request, plugin: UploadFile = File(...)):
    """Upload a plugin pack.

    Supported uploads:
      - .yaml/.yml: saved into plugins/providers/
      - .zip: may contain any of:
          * providers.yaml (root) or providers/*.yml/.yaml  (data-only provider packs)
          * python/providers/*.py and/or python/addons/*.py (only if SOCIAL_HUNT_ALLOW_PY_PLUGINS=1)

    IMPORTANT: python plugins execute arbitrary code in-process.
    """
    _require_admin(request)

    root = _ensure_plugin_dirs()

    filename = _safe_filename(plugin.filename or "plugin")
    raw = await plugin.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    # Small safety cap (web upload is meant for small plugin packs)
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="upload too large")

    ext = Path(filename).suffix.lower()
    installed: List[str] = []

    def _write_bytes(dest: Path, content: bytes):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        installed.append(str(dest.relative_to(root)))

    if ext in (".yaml", ".yml"):
        out = root / "providers" / f"{Path(filename).stem}.yaml"
        _write_bytes(out, raw)
    elif ext == ".zip":
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
        except Exception:
            raise HTTPException(status_code=400, detail="invalid zip")

        allow_py = _allow_py_plugins()
        found_py = False

        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                continue

            data = zf.read(info)
            lower = name.lower()

            # providers (data-only)
            if lower in ("providers.yaml", "providers.yml"):
                out = root / "providers" / f"{Path(filename).stem}__providers.yaml"
                _write_bytes(out, data)
                continue
            if lower.startswith("providers/") and (lower.endswith(".yaml") or lower.endswith(".yml")):
                out_name = _safe_filename(Path(lower).name)
                out = root / "providers" / f"{Path(filename).stem}__{out_name}"
                if not out.suffix:
                    out = out.with_suffix(".yaml")
                _write_bytes(out, data)
                continue

            # python providers/addons (optional)
            if lower.startswith("python/providers/") and lower.endswith(".py"):
                found_py = True
                if not allow_py:
                    continue
                out_name = _safe_filename(Path(lower).name)
                out = root / "python" / "providers" / f"{Path(filename).stem}__{out_name}"
                _write_bytes(out, data)
                continue

            if lower.startswith("python/addons/") and lower.endswith(".py"):
                found_py = True
                if not allow_py:
                    continue
                out_name = _safe_filename(Path(lower).name)
                out = root / "python" / "addons" / f"{Path(filename).stem}__{out_name}"
                _write_bytes(out, data)
                continue

        if found_py and not allow_py:
            # Make it clear why they don't show up.
            raise HTTPException(
                status_code=400,
                detail="zip contains python plugins but SOCIAL_HUNT_ALLOW_PY_PLUGINS is not enabled",
            )

        if not installed:
            raise HTTPException(status_code=400, detail="no valid plugin files found in zip")
    else:
        raise HTTPException(status_code=400, detail="unsupported file type (use .yaml or .zip)")

    # Hot-reload so new providers/addons show up immediately.
    reload_result = await _reload_engine()
    return {
        "installed": installed,
        "reloaded": reload_result,
        "plugins": list_installed_plugins(),
    }

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


def _dhash(img: Image.Image, size: int = 8) -> str:
    """Compute a simple dHash (difference hash) as a 16-char hex string."""
    w, h = size + 1, size
    im = img.convert("L").resize((w, h), Image.Resampling.LANCZOS)
    px = list(im.getdata())

    bits = 0
    bitpos = 0
    for row in range(h):
        row_start = row * w
        for col in range(size):
            left = px[row_start + col]
            right = px[row_start + col + 1]
            if left > right:
                bits |= 1 << bitpos
            bitpos += 1

    return f"{bits:016x}"


def _hamming_64(a_hex: str, b_hex: str) -> Optional[int]:
    try:
        a = int(a_hex, 16)
        b = int(b_hex, 16)
    except Exception:
        return None
    return (a ^ b).bit_count()


@app.post("/api/reverse_image")
async def api_reverse_image(req: ReverseImageRequest):
    """Reverse-image match *within an existing job's avatar set*.

    This is intentionally scoped: it compares the query image against the avatar
    fingerprints already collected for a given search job.
    """
    job = JOBS.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.get("state") != "done":
        raise HTTPException(status_code=400, detail="job not completed")

    image_url = (req.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url required")

    try:
        async with httpx.AsyncClient() as client:
            content, ctype = await safe_fetch_bytes(
                client,
                image_url,
                timeout=10.0,
                max_bytes=2_000_000,
                accept_prefix="image",
            )
        sha = hashlib.sha256(content).hexdigest()
        img = Image.open(io.BytesIO(content))
        dh = _dhash(img)
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=f"unsafe image_url: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"failed to fetch/parse image: {e}")

    matches = []
    for r in job.get("results") or []:
        prof = (r.get("profile") or {})
        rsha = prof.get("avatar_sha256")
        rdh = prof.get("avatar_dhash")
        if not rsha and not rdh:
            continue

        if rsha and rsha == sha:
            matches.append(
                {
                    "provider": r.get("provider"),
                    "url": r.get("url"),
                    "match_type": "sha256",
                    "distance": 0,
                }
            )
            continue

        if rdh and dh:
            dist = _hamming_64(str(rdh), dh)
            if dist is None:
                continue
            matches.append(
                {
                    "provider": r.get("provider"),
                    "url": r.get("url"),
                    "match_type": "dhash",
                    "distance": dist,
                }
            )

    matches.sort(key=lambda x: x.get("distance", 999999))

    return {
        "job_id": req.job_id,
        "query": {"image_url": image_url, "content_type": ctype, "sha256": sha, "dhash": dh},
        "matches": matches,
    }


def _build_reverse_links(image_url: str) -> List[Dict[str, str]]:
    u = quote(image_url, safe="")
    return [
        {"name": "Google Images", "url": f"https://www.google.com/searchbyimage?image_url={u}"},
        {"name": "Google Lens (desktop)", "url": f"https://lens.google.com/uploadbyurl?url={u}"},
        {"name": "Bing Visual Search", "url": f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={u}"},
        {"name": "TinEye", "url": f"https://tineye.com/search?url={u}"},
        {"name": "Yandex Images", "url": f"https://yandex.com/images/search?rpt=imageview&url={u}"},
    ]


@app.post("/api/reverse_image_links")
async def api_reverse_image_links(req: ReverseImageLinksRequest):
    image_url = (req.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url required")
    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="image_url must start with http:// or https://")
    return {"image_url": image_url, "links": _build_reverse_links(image_url)}

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
