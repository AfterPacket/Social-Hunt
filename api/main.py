from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.settings_store import SettingsStore, mask_for_client
from social_hunt.addons_registry import build_addon_registry, load_enabled_addons
from social_hunt.engine import SocialHuntEngine
from social_hunt.face_utils import image_to_base64_uri, restore_face
from social_hunt.plugin_loader import list_installed_plugins
from social_hunt.registry import build_registry, list_provider_names

app = FastAPI(title="Social-Hunt API", version="2.2.0")


@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    # Disable caching for all responses to ensure users always see the latest UI and data
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ---- paths ----
# Anchor all filesystem paths to the repo root so running from a different
# working directory (systemd, Docker, etc.) does not break persistence.
APP_ROOT = Path(__file__).resolve().parents[1]


def _resolve_env_path(env_name: str, default_rel: str) -> Path:
    v = (os.getenv(env_name) or "").strip()
    if not v:
        v = default_rel
    p = Path(v)
    return p if p.is_absolute() else (APP_ROOT / p).resolve()


WEB_DIR = (APP_ROOT / "web").resolve()
UPLOADS_DIR = (WEB_DIR / "temp_uploads").resolve()
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ---- settings store ----
SETTINGS_PATH = _resolve_env_path("SOCIAL_HUNT_SETTINGS_PATH", "data/settings.json")
settings_store = SettingsStore(str(SETTINGS_PATH))

# providers yaml (anchored)
PROVIDERS_YAML = _resolve_env_path("SOCIAL_HUNT_PROVIDERS_YAML", "providers.yaml")

JOBS_DIR = _resolve_env_path("SOCIAL_HUNT_JOBS_DIR", "data/jobs")
JOBS_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
async def on_startup():
    print(f"[INFO] Settings path: {SETTINGS_PATH}")
    env_token = (os.getenv("SOCIAL_HUNT_PLUGIN_TOKEN") or "").strip()
    if env_token:
        print(
            "[INFO] Admin token loaded from SOCIAL_HUNT_PLUGIN_TOKEN (env var). This overrides settings.json."
        )
    else:
        print("[INFO] Admin token loaded from settings.json.")


# ---- auth (simple admin token) ----
# Priority order:
#   1) SOCIAL_HUNT_PLUGIN_TOKEN env var (recommended for production)
#   2) admin_token stored in settings.json (can be set via the dashboard in bootstrap mode)
def _current_admin_token() -> str:
    env_token = (os.getenv("SOCIAL_HUNT_PLUGIN_TOKEN") or "").strip()
    if env_token:
        return env_token
    try:
        data = settings_store.load()
        return str(data.get("admin_token") or "").strip()
    except Exception:
        return ""


def require_admin(x_plugin_token: Optional[str]) -> None:
    token = _current_admin_token()
    if not token:
        raise HTTPException(
            status_code=500,
            detail=(
                "No admin token configured. Set SOCIAL_HUNT_PLUGIN_TOKEN (env var) "
                "or set admin_token via the Token page while bootstrap is enabled."
            ),
        )
    if not x_plugin_token or x_plugin_token != token:
        raise HTTPException(status_code=401, detail="Invalid token")


def _bootstrap_allowed(request: Request) -> bool:
    """Allow setting the admin token via the web UI only when explicitly enabled.

    Enable bootstrap by setting one of:
      - SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP=1
      - SOCIAL_HUNT_BOOTSTRAP_SECRET=<random> and providing it in the request
    """
    if (os.getenv("SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP") or "").strip() == "1":
        return True
    # Secret-based bootstrap (safer for remote)
    secret = (os.getenv("SOCIAL_HUNT_BOOTSTRAP_SECRET") or "").strip()
    if secret:
        provided = (request.headers.get("X-Bootstrap-Secret") or "").strip()
        return provided == secret
    return False


class AdminTokenPutReq(BaseModel):
    token: str


@app.get("/api/admin/status")
async def api_admin_status():
    env_token = (os.getenv("SOCIAL_HUNT_PLUGIN_TOKEN") or "").strip()
    settings_token = str(settings_store.load().get("admin_token") or "").strip()
    token = env_token or settings_token
    uploads = (os.getenv("SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD") or "0").strip() == "1"
    return {
        "admin_token_set": bool(token),
        "admin_token_source": "env"
        if env_token
        else ("settings" if settings_token else "none"),
        "web_plugin_upload_enabled": uploads,
        "bootstrap_env_enabled": (
            os.getenv("SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP") or ""
        ).strip()
        == "1",
        "bootstrap_secret_required": bool(
            (os.getenv("SOCIAL_HUNT_BOOTSTRAP_SECRET") or "").strip()
        ),
    }


@app.put("/api/admin/token")
async def api_admin_set_token(
    req: AdminTokenPutReq,
    request: Request,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    new_token = (req.token or "").strip()
    if not new_token:
        raise HTTPException(status_code=400, detail="token required")
    if len(new_token) < 20:
        raise HTTPException(status_code=400, detail="token too short (use >= 20 chars)")

    current = _current_admin_token()

    # If a token already exists, you must authenticate with it.
    if current:
        require_admin(x_plugin_token)
    else:
        # No token exists; only allow setting it when bootstrap is enabled.
        if not _bootstrap_allowed(request):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Bootstrap disabled. Set SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP=1 (temporary) "
                    "or set SOCIAL_HUNT_BOOTSTRAP_SECRET and send X-Bootstrap-Secret."
                ),
            )

    data = settings_store.load()
    data["admin_token"] = new_token
    settings_store.save(data)
    return {"ok": True}


@app.post("/api/admin/update")
async def api_admin_update(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Perform a git pull to update the application.
    Local changes to 'data/' are protected by .gitignore.
    """
    require_admin(x_plugin_token)
    try:
        # Protect local configuration and Docker files from being overwritten during pull
        to_protect = [
            "data/settings.json",
            "docker/Dockerfile",
            "docker/docker-compose.yml",
        ]
        for path in to_protect:
            subprocess.run(
                ["git", "update-index", "--assume-unchanged", path],
                cwd=str(APP_ROOT),
                capture_output=True,
            )

        proc = subprocess.run(
            ["git", "pull"], cwd=str(APP_ROOT), capture_output=True, text=True
        )

        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "message": "Update successful" if proc.returncode == 0 else "Update failed",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/admin/restart")
async def api_admin_restart(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Exit the current process so a supervisor (systemd, Docker, etc.) can restart it.
    """
    require_admin(x_plugin_token)

    async def _restart() -> None:
        await asyncio.sleep(0.75)
        os._exit(0)

    asyncio.create_task(_restart())
    return {
        "ok": True,
        "message": "Restarting server process. Reconnect in a few seconds.",
    }


# ---- core engine ----
registry = build_registry(str(PROVIDERS_YAML))
engine = SocialHuntEngine(registry, max_concurrency=6)


def reload_registry() -> None:
    global registry
    registry = build_registry(str(PROVIDERS_YAML))
    engine.registry = registry
    engine.addon_registry = build_addon_registry()
    engine.enabled_addon_names = load_enabled_addons()


# ---- simple in-memory job store (swap to Redis for production) ----
JOBS: Dict[str, Dict[str, Any]] = {}


def _summarize_results(results: List[Dict[str, Any]]) -> Dict[str, int]:
    total = len(results)
    found = 0
    failed = 0
    for r in results:
        status = (r or {}).get("status")
        if status == "found":
            found += 1
        elif status in ("error", "unknown", "blocked"):
            failed += 1
    return {"results_count": total, "found_count": found, "failed_count": failed}


def _save_job_to_disk(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return
    try:
        path = JOBS_DIR / f"{job_id}.json"
        path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed to save job {job_id}: {e}")


def _load_job_from_disk(job_id: str) -> Optional[Dict[str, Any]]:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class SearchRequest(BaseModel):
    username: str
    providers: Optional[List[str]] = None


@app.get("/api/providers")
async def api_providers():
    return {"providers": list_provider_names(registry)}


@app.post("/api/providers/reload")
async def api_providers_reload(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
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

    from social_hunt.demo import is_demo_mode

    return {
        "client_ip": ip,
        "via": "x-forwarded-for" if xff else ("x-real-ip" if xri else "socket"),
        "user_agent": request.headers.get("user-agent", ""),
        "demo_mode": is_demo_mode(),
    }


@app.post("/api/search")
async def api_search(req: SearchRequest):
    username = (req.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")

    # basic sanity cap (avoid accidental huge input)
    if len(username) > 64:
        raise HTTPException(status_code=400, detail="username too long")

    if req.providers:
        chosen = [p for p in req.providers if p in registry]
    else:
        chosen = list(registry.keys())

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "ts": int(time.time()),
        "state": "running",
        "results": [],
        "username": username,
        "providers_count": len(chosen),
        "results_count": 0,
        "found_count": 0,
        "failed_count": 0,
    }

    def progress(res):
        if job_id in JOBS:
            job = JOBS[job_id]
            job["results"].append(res.to_dict())
            job["results_count"] = int(job.get("results_count", 0)) + 1
            status = getattr(res, "status", None)
            status_val = status.value if status is not None else None
            if status_val == "found":
                job["found_count"] = int(job.get("found_count", 0)) + 1
            elif status_val in ("error", "unknown", "blocked"):
                job["failed_count"] = int(job.get("failed_count", 0)) + 1

    async def runner():
        try:
            final_res = await engine.scan_username(
                username, req.providers, progress_callback=progress
            )
            final_dicts = [r.to_dict() for r in final_res]
            JOBS[job_id]["results"] = final_dicts
            JOBS[job_id]["state"] = "done"
            JOBS[job_id].update(_summarize_results(final_dicts))
        except Exception as e:
            JOBS[job_id]["state"] = "failed"
            JOBS[job_id]["error"] = str(e)
        finally:
            _save_job_to_disk(job_id)

    asyncio.create_task(runner())
    return {"job_id": job_id}


@app.post("/api/face/unmask")
async def api_face_unmask(file: UploadFile = File(...), strength: float = Form(0.5)):
    """
    Experimental: Unmask/Restore a face using an external AI service.
    Requires SOCIAL_HUNT_FACE_AI_URL to be pointing to a compatible AI worker
    running a model like CodeFormer or GFPGAN.
    """
    try:
        content = await file.read()
        restored_bytes = await restore_face(content, strength=strength)

        if not restored_bytes:
            raise HTTPException(
                status_code=500,
                detail="Face restoration failed. Ensure the AI service is running and accessible.",
            )

        return {"success": True, "image": image_to_base64_uri(restored_bytes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str, limit: Optional[int] = None):
    job = JOBS.get(job_id)
    if not job:
        # try disk
        job = _load_job_from_disk(job_id)
        if job:
            JOBS[job_id] = job

    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job_out = dict(job)
    results = job_out.get("results") or []
    summary = _summarize_results(results)
    job_out.setdefault("results_count", summary["results_count"])
    job_out.setdefault("found_count", summary["found_count"])
    job_out.setdefault("failed_count", summary["failed_count"])
    total = summary["results_count"]

    if limit is not None:
        try:
            limit_val = int(limit)
        except Exception:
            limit_val = None
        if limit_val is not None and limit_val >= 0 and total > limit_val:
            job_out["results"] = results[:limit_val]
            job_out["results_total"] = total
        else:
            job_out["results_total"] = total
    else:
        job_out["results_total"] = total

    return job_out


@app.post("/api/face-search")
async def api_face_search(
    username: str = Form(...),
    files: List[UploadFile] = File(...),
):
    username = (username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "id": job_id,
        "ts": int(time.time()),
        "state": "running",
        "results": [],
        "username": username,
        "providers_count": len(list(registry.keys())),
        "results_count": 0,
        "found_count": 0,
        "failed_count": 0,
    }

    # Create a temporary directory for the uploaded images
    temp_dir = APP_ROOT / "temp" / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    image_paths = []
    for file in files:
        try:
            # Sanitize filename
            filename = _safe_name(file.filename)
            file_path = temp_dir / filename
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            image_paths.append(str(file_path))
        except Exception:
            # Handle file saving errors
            JOBS[job_id]["state"] = "failed"
            JOBS[job_id]["error"] = "Failed to save uploaded file."
            return {"job_id": job_id}

    from social_hunt.addons.face_matcher import FaceMatcherAddon

    face_matcher_addon = FaceMatcherAddon(target_image_paths=image_paths)

    def progress(res):
        if job_id in JOBS:
            job = JOBS[job_id]
            job["results"].append(res.to_dict())
            job["results_count"] = int(job.get("results_count", 0)) + 1
            status = getattr(res, "status", None)
            status_val = status.value if status is not None else None
            if status_val == "found":
                job["found_count"] = int(job.get("found_count", 0)) + 1
            elif status_val in ("error", "unknown", "blocked"):
                job["failed_count"] = int(job.get("failed_count", 0)) + 1

    async def runner():
        try:
            final_res = await engine.scan_username(
                username,
                dynamic_addons=[face_matcher_addon],
                progress_callback=progress,
            )
            final_dicts = [r.to_dict() for r in final_res]
            JOBS[job_id]["results"] = final_dicts
            JOBS[job_id]["state"] = "done"
            JOBS[job_id].update(_summarize_results(final_dicts))
        except Exception as e:
            JOBS[job_id]["state"] = "failed"
            JOBS[job_id]["error"] = str(e)
        finally:
            _save_job_to_disk(job_id)

            # Clean up the temporary files
            for path in image_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass

    asyncio.create_task(runner())
    return {"job_id": job_id}


# ---------------------------
# Reverse image search links
# ---------------------------


def _build_reverse_links(image_url: str) -> List[Dict[str, str]]:
    from urllib.parse import quote_plus

    u = image_url.strip()
    q = quote_plus(u)

    # Note: some endpoints change over time; these are common URL-entry points.
    return [
        {
            "name": "Google Images",
            "url": f"https://www.google.com/searchbyimage?image_url={q}",
        },
        {"name": "Google Lens", "url": f"https://lens.google.com/uploadbyurl?url={q}"},
        {"name": "TinEye", "url": f"https://tineye.com/search?url={q}"},
        {
            "name": "Bing Visual Search",
            "url": f"https://www.bing.com/images/search?q=imgurl:{q}&view=detailv2&iss=sbi",
        },
        {
            "name": "Yandex Images",
            "url": f"https://yandex.com/images/search?rpt=imageview&url={q}",
        },
        {"name": "PimEyes (Manual Upload)", "url": "https://pimeyes.com/en"},
        {"name": "FaceCheck.ID (Manual Upload)", "url": "https://facecheck.id/"},
        {"name": "Face-Spy (Manual Upload)", "url": "https://face-spy.com/"},
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


@app.post("/api/reverse_image_upload")
async def api_reverse_image_upload(request: Request, file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename = (file.filename or "image.jpg").lower()
    valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    if not any(filename.endswith(ext) for ext in valid_exts):
        raise HTTPException(
            status_code=400,
            detail="Invalid image extension. Use jpg, png, gif, webp, bmp.",
        )

    ext = Path(filename).suffix
    safe_name = f"{uuid.uuid4()}{ext}"
    out_path = UPLOADS_DIR / safe_name

    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File too large (>10MB)")

        out_path.write_bytes(content)
    except Exception as e:
        print(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Construct public URL
    # Preference: Env Var > Settings > Request Base URL
    public_base = (os.getenv("SOCIAL_HUNT_PUBLIC_URL") or "").strip()
    if not public_base:
        try:
            public_base = str(settings_store.load().get("public_url") or "").strip()
        except Exception:
            pass

    if not public_base:
        public_base = str(request.base_url)

    if not public_base.endswith("/"):
        public_base += "/"

    file_url = f"{public_base}uploads/{safe_name}"

    # Heuristic check for private URLs (warns user if running locally without a tunnel)
    is_private = any(
        x in file_url
        for x in ["localhost", "127.0.0.1", "0.0.0.0", "192.168.", "10.", "172.16."]
    )

    # If private, try to upload to catbox.moe (temporary hosting) so external tools can see it
    if is_private:
        try:
            import httpx

            print("[INFO] Private IP detected. Attempting upload to catbox.moe...")
            async with httpx.AsyncClient() as client:
                data = {"reqtype": "fileupload"}
                files = {
                    "fileToUpload": (
                        filename,
                        content,
                        file.content_type or "application/octet-stream",
                    )
                }
                resp = await client.post(
                    "https://catbox.moe/user/api.php",
                    data=data,
                    files=files,
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    c_url = resp.text.strip()
                    if c_url.startswith("http"):
                        file_url = c_url
                        is_private = False  # Successfully publicly hosted
        except Exception as e:
            print(f"[WARN] Catbox upload failed: {e}")

    return {
        "links": _build_reverse_links(file_url),
        "image_url": file_url,
        "is_private_ip": is_private,
    }


# ---------------------------
# Settings (dynamic)
# ---------------------------


@app.get("/api/settings")
async def api_get_settings(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)
    data = settings_store.load()
    return {"settings": mask_for_client(data)}


class SettingsPutReq(BaseModel):
    settings: Dict[str, Any]


@app.put("/api/settings")
async def api_put_settings(
    req: SettingsPutReq,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
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


PLUGIN_DIR = _resolve_env_path("SOCIAL_HUNT_PLUGIN_DIR", "plugins/providers")
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


def _install_py_bytes(category: str, filename: str, data: bytes) -> str:
    # category is "providers" or "addons"
    # target: plugins/python/{category}
    target_dir = APP_ROOT / "plugins" / "python" / category
    target_dir.mkdir(parents=True, exist_ok=True)

    out_name = _safe_name(Path(filename).name)
    if not out_name.endswith(".py"):
        out_name += ".py"

    out_path = target_dir / out_name
    print(f"[UPLOAD] Installing python plugin: {out_path}")
    out_path.write_bytes(data)
    return str(out_path)


def _extract_plugins_from_zip(zbytes: bytes) -> List[str]:
    installed: List[str] = []
    allow_py = os.getenv("SOCIAL_HUNT_ALLOW_PY_PLUGINS", "").strip() == "1"
    print(f"[UPLOAD] Extracting ZIP. allow_py={allow_py}")

    with zipfile.ZipFile(BytesIO(zbytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            # block traversal
            if name.startswith("/") or ".." in name:
                print(f"[UPLOAD] SKIP (unsafe path): {name}")
                continue
            lower = name.lower()
            data = z.read(info)
            fname = Path(name).name
            print(f"[UPLOAD] Processing zip entry: {name}")

            if lower.endswith(".yaml") or lower.endswith(".yml"):
                installed.append(_install_yaml_bytes(fname, data))

            elif allow_py and lower.endswith(".py"):
                # Expect python/providers/*.py or python/addons/*.py
                if "python/providers/" in name:
                    installed.append(_install_py_bytes("providers", fname, data))
                elif "python/addons/" in name:
                    installed.append(_install_py_bytes("addons", fname, data))
                else:
                    print(f"[UPLOAD] SKIP (py not in correct folder): {name}")
            elif lower.endswith(".py") and not allow_py:
                print(f"[UPLOAD] SKIP (py disabled): {name}")

    return installed


@app.get("/api/plugin/list")
async def api_plugin_list(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    if (os.getenv("SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD") or "0").strip() != "1":
        raise HTTPException(
            status_code=403,
            detail="Plugin management is disabled",
        )
    require_admin(x_plugin_token)
    return list_installed_plugins()


@app.post("/api/plugin/upload")
async def api_plugin_upload(
    file: UploadFile = File(...),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    # Extra safety: web uploads are disabled unless explicitly enabled
    if (os.getenv("SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD") or "0").strip() != "1":
        raise HTTPException(
            status_code=403,
            detail="Web plugin uploads are disabled (set SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1 and restart)",
        )
    require_admin(x_plugin_token)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    fname = (file.filename or "plugin").strip()
    lower = fname.lower()
    print(f"[UPLOAD] Received file: {fname} ({len(raw)} bytes)")

    installed: List[str] = []

    # Limit upload size ~2MB
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="upload too large")

    if lower.endswith(".zip"):
        installed = _extract_plugins_from_zip(raw)
    elif lower.endswith(".yaml") or lower.endswith(".yml"):
        installed = [_install_yaml_bytes(fname, raw)]
    else:
        print("[UPLOAD] Rejected: invalid extension")
        raise HTTPException(status_code=400, detail="upload must be .yaml/.yml or .zip")

    print(f"[UPLOAD] Installed files: {installed}")
    reload_registry()

    return {
        "ok": True,
        "installed": installed,
        "providers": list_provider_names(registry),
    }


class PluginDeleteReq(BaseModel):
    name: str


@app.post("/api/plugin/delete")
async def api_plugin_delete(
    req: PluginDeleteReq,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    if (os.getenv("SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD") or "0").strip() != "1":
        raise HTTPException(
            status_code=403,
            detail="Plugin management is disabled",
        )
    require_admin(x_plugin_token)

    # Basic path safety
    name = req.name.replace("\\", "/")
    if ".." in name:
        raise HTTPException(status_code=400, detail="Invalid plugin name")

    plugins_root = _resolve_env_path("SOCIAL_HUNT_PLUGINS_DIR", "plugins").resolve()
    target = (plugins_root / name).resolve()

    print(f"[DELETE] Root: {plugins_root}")
    print(f"[DELETE] Target: {target}")
    print(f"[DELETE] Name param: {name}")

    # Robust check for path containment
    try:
        target.relative_to(plugins_root)
    except ValueError:
        print(f"[DELETE] Path traversal detected for {target} vs {plugins_root}")
        raise HTTPException(status_code=400, detail="Path traversal detected")

    if not target.exists():
        print(f"[DELETE] Target does not exist: {target}")
        raise HTTPException(status_code=404, detail=f"Plugin not found: {name}")

    if not target.is_file():
        raise HTTPException(status_code=400, detail="Target is not a file")

    try:
        os.remove(target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    reload_registry()

    return {"ok": True, "deleted": name}


@app.post("/api/demask")
async def api_demask(
    file: UploadFile = File(...),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    AI demasking using Replicate library for automatic version management.
    Performs mask removal followed by face restoration for forensic clarity.
    """
    require_admin(x_plugin_token)

    # 1. Get Replicate API Token
    settings = settings_store.load()
    replicate_token = (os.getenv("REPLICATE_API_TOKEN") or "").strip() or settings.get(
        "replicate_api_token"
    )
    if isinstance(replicate_token, dict):
        replicate_token = replicate_token.get("value")

    if not replicate_token:
        try:
            content = await file.read()
            restored_bytes = await restore_face(content, strength=0.7)
            if restored_bytes:
                from fastapi.responses import StreamingResponse

                return StreamingResponse(
                    BytesIO(restored_bytes), media_type="image/png"
                )
        except Exception as e:
            print(f"[DEBUG] Local demask fallback failed: {e}")

        raise HTTPException(
            status_code=400,
            detail="AI service unavailable. Configure REPLICATE_API_TOKEN or SOCIAL_HUNT_FACE_AI_URL.",
        )

    try:
        # 2. Prepare the image
        content = await file.read()
        print(f"[DEBUG] Demasking: processing {file.filename}")

        # Upload to Catbox for reliability (Replicate handles URLs better)
        file_url = ""
        try:
            async with httpx.AsyncClient() as hc:
                files = {"fileToUpload": (file.filename, content, file.content_type)}
                data = {"reqtype": "fileupload", "userhash": ""}
                cres = await hc.post(
                    "https://catbox.moe/user/api.php", data=data, files=files
                )
                if cres.status_code == 200:
                    file_url = cres.text.strip()
                    print(f"[DEBUG] Demasking: uploaded to {file_url}")
        except Exception as e:
            print(f"[WARN] Demasking: Catbox upload failed: {e}")

        image_input = file_url if file_url else BytesIO(content)

        # 3. Step 1: Remove the mask using Pix2Pix
        # Using raw HTTP to match the working curl example exactly
        print("[DEBUG] Demasking: step 1 (instruct-pix2pix)...")

        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Token {replicate_token}",
                "Content-Type": "application/json",
            }

            # Use the exact payload structure from the working curl
            payload = {
                "version": "30c1d0b916a6f8efce20493f5d61ee27491ab2a60437c13c588468b9810ec23f",
                "input": {
                    "image": file_url
                    if file_url
                    else f"data:{file.content_type};base64,{base64.b64encode(content).decode()}",
                    "prompt": "remove the face mask, reveal the underlying face, forensic detail, high quality",
                    "negative_prompt": "blurry, distorted, mask remains",
                    "num_inference_steps": 30,
                },
            }

            res = await client.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            if res.status_code != 201:
                print(f"[ERROR] Demasking Step 1 failed: {res.text}")
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Replicate API Error: {res.text}",
                )

            prediction = res.json()
            poll_url = prediction["urls"]["get"]

            # Poll for result
            inpainted_url = ""
            start_time = time.time()
            while time.time() - start_time < 90:
                poll_res = await client.get(poll_url, headers=headers)
                status_data = poll_res.json()
                status = status_data["status"]

                if status == "succeeded":
                    out = status_data["output"]
                    inpainted_url = out[0] if isinstance(out, list) else out
                    break
                elif status == "failed":
                    raise HTTPException(
                        status_code=500,
                        detail=f"AI Step 1 failed: {status_data.get('error')}",
                    )

                await asyncio.sleep(2)

            if not inpainted_url:
                raise HTTPException(status_code=504, detail="AI Step 1 timed out.")
        print(f"[DEBUG] Demasking: step 1 complete, url: {inpainted_url}")

        # 4. Step 2: Face Restoration (CodeFormer)
        print("[DEBUG] Demasking: step 2 (codeformer)...")
        try:
            payload_cf = {
                "version": "7de2ea4a352033cfa2f21683c7a9511da922ec5ad9f9e61298d0b3dd16742617",
                "input": {
                    "image": inpainted_url,
                    "upscale": 1,
                    "face_upsample": True,
                    "codeformer_fidelity": 0.7,
                },
            }

            async with httpx.AsyncClient() as client:
                res_cf = await client.post(
                    "https://api.replicate.com/v1/predictions",
                    headers=headers,
                    json=payload_cf,
                    timeout=60.0,
                )
                if res_cf.status_code == 201:
                    pred_cf = res_cf.json()
                    poll_url_cf = pred_cf["urls"]["get"]

                    final_output_url = ""
                    start_time = time.time()
                    while time.time() - start_time < 90:
                        p_res = await client.get(poll_url_cf, headers=headers)
                        s_data = p_res.json()
                        if s_data["status"] == "succeeded":
                            final_output_url = s_data["output"]
                            break
                        elif s_data["status"] == "failed":
                            break
                        await asyncio.sleep(2)

                    if final_output_url:
                        img_res = await client.get(final_output_url)
                        return StreamingResponse(
                            BytesIO(img_res.content), media_type="image/png"
                        )

            # Fallback to step 1 result
            async with httpx.AsyncClient() as hc:
                img_res = await hc.get(inpainted_url)
                return StreamingResponse(
                    BytesIO(img_res.content), media_type="image/png"
                )
        except Exception as e:
            print(f"[WARN] Demasking Step 2 failed: {e}. Returning Step 1 result.")
            async with httpx.AsyncClient() as hc:
                img_res = await hc.get(inpainted_url)
                return StreamingResponse(
                    BytesIO(img_res.content), media_type="image/png"
                )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Demasking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---- UI ----
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/")
async def root():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.post("/api/auth/verify")
async def api_auth_verify(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)
    return {"ok": True}


@app.get("/api/public/theme")
async def api_public_theme():
    """Returns the current theme name without requiring authentication."""
    data = settings_store.load()
    theme = data.get("theme")
    if isinstance(theme, dict):
        return {"theme": theme.get("value") or "default"}
    return {"theme": theme or "default"}


@app.get("/login")
async def login_page():
    return FileResponse(str(WEB_DIR / "login.html"))
