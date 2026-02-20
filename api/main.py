# main.py
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import replicate
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.settings_store import SECRET_KEYS_FIELD, SettingsStore, mask_for_client
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


@app.get("/sh-api/admin/status")
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


@app.put("/sh-api/admin/token")
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


@app.post("/sh-api/admin/update")
async def api_admin_update(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Perform a git pull to update the application.
    Local changes to 'data/' are protected by .gitignore.
    """
    require_admin(x_plugin_token)
    try:
        req_path = APP_ROOT / "requirements.txt"
        before_requirements = None
        if req_path.exists():
            before_requirements = req_path.read_text(encoding="utf-8", errors="ignore")

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

        after_requirements = None
        if req_path.exists():
            after_requirements = req_path.read_text(encoding="utf-8", errors="ignore")

        pip_ran = False
        pip_ok = True
        pip_stdout = ""
        pip_stderr = ""
        if proc.returncode == 0 and before_requirements != after_requirements:
            pip_ran = True
            pip_proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
                cwd=str(APP_ROOT),
                capture_output=True,
                text=True,
            )
            pip_ok = pip_proc.returncode == 0
            pip_stdout = pip_proc.stdout
            pip_stderr = pip_proc.stderr

        ok = proc.returncode == 0 and pip_ok
        message = "Update successful" if ok else "Update failed"
        if proc.returncode == 0 and pip_ran and not pip_ok:
            message = "Update pulled, but requirements install failed"

        return {
            "ok": ok,
            "stdout": (proc.stdout or "") + ("\n" + pip_stdout if pip_stdout else ""),
            "stderr": (proc.stderr or "") + ("\n" + pip_stderr if pip_stderr else ""),
            "message": message,
            "pip_ran": pip_ran,
            "pip_ok": pip_ok,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/sh-api/admin/restart")
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
        elif status in ("error", "unknown", "blocked", "not_found"):
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


@app.get("/sh-api/providers")
async def api_providers():
    return {"providers": list_provider_names(registry)}


@app.post("/sh-api/providers/reload")
async def api_providers_reload(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)
    reload_registry()
    return {"ok": True, "providers": list_provider_names(registry)}


@app.get("/sh-api/whoami")
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


@app.post("/sh-api/search")
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
            elif status_val in ("error", "unknown", "blocked", "not_found"):
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


@app.post("/sh-api/face/unmask")
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


@app.get("/sh-api/jobs/{job_id}")
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


@app.post("/sh-api/face-search")
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
            elif status_val in ("error", "unknown", "blocked", "not_found"):
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


@app.post("/sh-api/reverse_image_links")
async def api_reverse_image_links(req: ReverseImageReq):
    image_url = (req.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url required")
    if not re.match(r"^https?://", image_url, re.I):
        raise HTTPException(status_code=400, detail="image_url must be http(s)")
    return {"links": _build_reverse_links(image_url)}


@app.post("/sh-api/reverse_image_upload")
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


@app.get("/sh-api/settings")
async def api_get_settings(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)
    data = settings_store.load()
    return {"settings": mask_for_client(data)}


class SettingsPutReq(BaseModel):
    settings: Dict[str, Any]


@app.put("/sh-api/settings")
async def api_put_settings(
    req: SettingsPutReq,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)

    if not isinstance(req.settings, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")

    current = settings_store.load()
    for k, v in req.settings.items():
        key = str(k)
        # allow deleting by setting null
        if v is None:
            current.pop(key, None)
            continue
        if key == SECRET_KEYS_FIELD:
            if isinstance(v, list):
                current[key] = [str(x) for x in v if str(x).strip()]
            continue
        # allow clearing by empty string
        current[key] = v

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


@app.get("/sh-api/plugin/list")
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


@app.post("/sh-api/plugin/upload")
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


@app.post("/sh-api/plugin/delete")
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


def _generate_face_coverage_mask(image_bytes: bytes) -> bytes:
    """
    Generate a PNG inpainting mask that covers the face-covering region
    (gaiter, balaclava, surgical mask, ski mask, etc.) in WHITE.
    Everything outside the mask stays BLACK and is left pixel-perfect by
    the inpainting model.

    Detection priority:
      1. face_recognition (dlib CNN) — handles partially occluded faces well
      2. OpenCV Haar cascade (frontal + profile) — fast backup
      3. Head-region heuristic — upper-centre of image when all detectors fail
         (people wearing full gaiters/balaclavas have no detectable facial
          features so classic detectors always miss them; the heuristic places
          a generous mask where a head is statistically most likely to appear)

    The mask covers from roughly eye-level down through the chin so that
    forehead, hair and eyebrows remain untouched — those are the identity
    cues that constrain the inpainting model and prevent gender swaps.
    """
    import cv2
    import numpy as np
    from PIL import Image as PILImage
    from PIL import ImageDraw, ImageFilter

    # ── decode image ──────────────────────────────────────────────────────────
    pil_img = PILImage.open(BytesIO(image_bytes)).convert("RGB")
    w_img, h_img = pil_img.size

    # face_locations returns (top, right, bottom, left) in CSS order
    face_boxes: list[tuple[int, int, int, int]] = []  # (top, right, bottom, left)

    # ── 1. face_recognition (dlib) ────────────────────────────────────────────
    try:
        import face_recognition
        import numpy as np_fr

        img_array = np_fr.array(pil_img)
        # "cnn" model is more robust on occluded/angled faces; fall back to
        # "hog" if dlib was built without CUDA to keep latency acceptable.
        try:
            locations = face_recognition.face_locations(img_array, model="cnn")
        except Exception:
            locations = face_recognition.face_locations(img_array, model="hog")

        if locations:
            face_boxes = list(locations)
            print(f"[Demask] face_recognition found {len(face_boxes)} face(s).")
    except Exception as e:
        print(f"[Demask] face_recognition unavailable ({e}); trying OpenCV.")

    # ── 2. OpenCV Haar cascade fallback ───────────────────────────────────────
    if not face_boxes:
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_cv is not None:
                gray = cv2.equalizeHist(cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY))

                for cascade_name in (
                    "haarcascade_frontalface_default.xml",
                    "haarcascade_frontalface_alt2.xml",
                    "haarcascade_profileface.xml",
                ):
                    cascade = cv2.CascadeClassifier(
                        cv2.data.haarcascades + cascade_name
                    )
                    detected = cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.05,
                        minNeighbors=3,
                        minSize=(50, 50),
                    )
                    if len(detected) > 0:
                        # Convert OpenCV (x,y,w,h) → (top,right,bottom,left)
                        for fx, fy, fw, fh in detected:
                            face_boxes.append((fy, fx + fw, fy + fh, fx))
                        print(
                            f"[Demask] OpenCV ({cascade_name}) found "
                            f"{len(face_boxes)} face(s)."
                        )
                        break
        except Exception as e:
            print(f"[Demask] OpenCV cascade failed ({e}).")

    # ── 3. Head-region heuristic (fully occluded face fallback) ───────────────
    # When someone wears a full gaiter + cap, zero facial features are exposed
    # so any detector will fail.  We place a generous mask in the upper-centre
    # of the frame — statistically where a head appears in portrait/bust shots.
    if not face_boxes:
        print(
            "[Demask] No face detected (subject likely fully covered). "
            "Applying head-region heuristic mask."
        )
        # Upper-centre band: horizontally centred, spanning ~15 %–70 % of height
        pad_x = int(w_img * 0.20)
        top_y = int(h_img * 0.10)
        bot_y = int(h_img * 0.72)
        face_boxes = [(top_y, w_img - pad_x, bot_y, pad_x)]

    # ── Build mask ────────────────────────────────────────────────────────────
    mask = PILImage.new("L", (w_img, h_img), 0)
    draw = ImageDraw.Draw(mask)

    for top, right, bottom, left in face_boxes:
        fh = bottom - top
        fw = right - left

        # Cover from ~30 % below the top of the face box (eye-line) down to
        # just below the chin.  Widen by 10 % on each side to catch jaw edges.
        pad_x = int(fw * 0.10)
        mask_top = top + int(fh * 0.30)
        mask_bottom = min(h_img, bottom + int(fh * 0.06))
        mask_left = max(0, left - pad_x)
        mask_right = min(w_img, right + pad_x)

        draw.rectangle([mask_left, mask_top, mask_right, mask_bottom], fill=255)

    # Feather edges so the inpainted region blends naturally at boundaries
    mask = mask.filter(ImageFilter.GaussianBlur(radius=8))
    mask = mask.point(lambda p: 255 if p > 25 else 0)

    buf = BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


@app.post("/sh-api/demask")
async def api_demask(
    file: UploadFile = File(...),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    AI demasking pipeline (Replicate):

    Step 1 — SD Inpainting (stability-ai/stable-diffusion-inpainting)
        An OpenCV face detector auto-generates a tight mask over the
        face-covering region.  SD inpainting ONLY modifies that region,
        so hair, forehead, skin tone, eyebrows and all surrounding identity
        cues are preserved — this is what prevents gender swaps and
        full-image hallucinations.

    Step 2 — CodeFormer face restoration (fidelity 0.5)
        Sharpens the inpainted face region.  Fidelity is kept at 0.5 so
        CodeFormer enhances rather than replaces the generated face.

    Fallback — If SD inpainting is unavailable, instruct-pix2pix is tried
        with tighter guidance values before giving up.
    """
    require_admin(x_plugin_token)

    # ── 1. Replicate token ────────────────────────────────────────────────────
    settings = settings_store.load()
    replicate_token = (os.getenv("REPLICATE_API_TOKEN") or "").strip() or settings.get(
        "replicate_api_token"
    )
    if isinstance(replicate_token, dict):
        replicate_token = replicate_token.get("value")

    if not replicate_token:
        # Try local face-restoration service as last resort
        try:
            content = await file.read()
            restored_bytes = await restore_face(content, strength=0.7)
            if restored_bytes:
                return StreamingResponse(
                    BytesIO(restored_bytes), media_type="image/png"
                )
        except Exception as e:
            print(f"[Demask] Local fallback failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="AI service unavailable. Configure REPLICATE_API_TOKEN in Settings.",
        )

    try:
        # ── 2. Read & encode image ────────────────────────────────────────────
        content = await file.read()
        print(f"[Demask] Processing: {file.filename}  ({len(content)} bytes)")

        mime = file.content_type or "image/jpeg"
        b64_img = f"data:{mime};base64,{base64.b64encode(content).decode()}"

        rep_client = replicate.Client(api_token=replicate_token)

        # ── 3. Auto-generate face coverage mask ───────────────────────────────
        print("[Demask] Generating face coverage mask…")
        mask_bytes = await asyncio.to_thread(_generate_face_coverage_mask, content)
        b64_mask = f"data:image/png;base64,{base64.b64encode(mask_bytes).decode()}"
        print("[Demask] Mask generated.")

        # ── 4. Fetch model versions ───────────────────────────────────────────
        inpaint_model_id = "stability-ai/stable-diffusion-inpainting"
        codeformer_model_id = "sczhou/codeformer"

        try:
            m_inpaint = await asyncio.to_thread(rep_client.models.get, inpaint_model_id)
            m_codeformer = await asyncio.to_thread(
                rep_client.models.get, codeformer_model_id
            )
            v_inpaint = m_inpaint.latest_version.id
            v_codeformer = m_codeformer.latest_version.id
        except Exception as me:
            print(
                f"[Demask] Could not fetch model metadata: {me} — using pinned versions."
            )
            v_inpaint = (
                "a9758cbfbd5f3c2094457d996681af52552901775aa2d6dd0b17fd15df959bef"
            )
            v_codeformer = (
                "7de2ea4a352033cfa2f21683c7a9511da922ec5ad9f9e61298d0b3dd16742617"
            )

        # ── 5. Step 1: SD Inpainting — only the masked region changes ─────────
        print("[Demask] Step 1 — SD inpainting…")
        inpainted_url = ""
        try:
            output_1 = await asyncio.to_thread(
                rep_client.run,
                f"{inpaint_model_id}:{v_inpaint}",
                input={
                    "image": b64_img,
                    "mask": b64_mask,
                    # Prompt: describe the TARGET state of the masked region only
                    "prompt": (
                        "realistic human face, natural skin, clear facial features, "
                        "photo-realistic, no face covering, no mask, no balaclava, "
                        "consistent skin tone, same ethnicity, same gender"
                    ),
                    "negative_prompt": (
                        "mask, balaclava, ski mask, face covering, sunglasses, "
                        "different gender, different ethnicity, distorted, blurry, "
                        "cartoon, painting, extra faces, mutation, deformed, "
                        "bad anatomy, watermark, text"
                    ),
                    "num_outputs": 1,
                    "num_inference_steps": 50,
                    "guidance_scale": 7.5,
                    # scheduler: DPMSolverMultistep gives crisp faces
                    "scheduler": "DPMSolverMultistep",
                },
            )
            if isinstance(output_1, list) and len(output_1) > 0:
                inpainted_url = str(output_1[0])
            else:
                inpainted_url = str(output_1) if output_1 else ""
        except Exception as e:
            print(f"[Demask] SD inpainting failed: {e}")

        # ── 5b. Fallback: pix2pix with corrected guidance values ─────────────
        if not inpainted_url:
            print("[Demask] Falling back to instruct-pix2pix…")
            try:
                m_p2p = await asyncio.to_thread(
                    rep_client.models.get, "timothybrooks/instruct-pix2pix"
                )
                v_p2p = m_p2p.latest_version.id
            except Exception:
                v_p2p = (
                    "30c1d0b916a6f8efce20493f5d61ee27491ab2a60437c13c588468b9810ec23f"
                )

            try:
                output_fb = await asyncio.to_thread(
                    rep_client.run,
                    f"timothybrooks/instruct-pix2pix:{v_p2p}",
                    input={
                        "image": b64_img,
                        "prompt": (
                            "reveal the face beneath the mask or covering; "
                            "keep gender, ethnicity, hair, clothing and background "
                            "completely unchanged; realistic photo"
                        ),
                        "negative_prompt": (
                            "change gender, change ethnicity, new person, hallucinate, "
                            "different identity, extra faces, distorted, cartoon, blurry, "
                            "mask remains, sunglasses, face covering"
                        ),
                        "num_inference_steps": 50,
                        # Higher image_guidance preserves structure; higher guidance
                        # makes the model actually follow the instruction
                        "image_guidance_scale": 2.0,
                        "guidance_scale": 8.0,
                    },
                )
                if isinstance(output_fb, list) and len(output_fb) > 0:
                    inpainted_url = str(output_fb[0])
                else:
                    inpainted_url = str(output_fb) if output_fb else ""
            except Exception as e2:
                print(f"[Demask] pix2pix fallback also failed: {e2}")

        if not inpainted_url:
            raise HTTPException(
                status_code=500, detail="Step 1 (inpainting) produced no output."
            )

        print(f"[Demask] Step 1 complete → {inpainted_url}")

        # ── 6. Step 2: CodeFormer — sharpen the inpainted face ───────────────
        # fidelity=0.5 means CodeFormer ENHANCES the existing face rather than
        # replacing it wholesale (fidelity=1.0 was causing gender swaps).
        print("[Demask] Step 2 — CodeFormer…")
        try:
            output_2 = await asyncio.to_thread(
                rep_client.run,
                f"{codeformer_model_id}:{v_codeformer}",
                input={
                    "image": inpainted_url,
                    "upscale": 1,
                    "face_upsample": True,
                    "codeformer_fidelity": 0.5,  # 0.5 = enhance, not replace
                },
            )
            if isinstance(output_2, list) and len(output_2) > 0:
                final_url = str(output_2[0])
            else:
                final_url = str(output_2) if output_2 else None

            fetch_url = final_url if final_url else inpainted_url
            async with httpx.AsyncClient() as hc:
                img_res = await hc.get(fetch_url)
            return StreamingResponse(BytesIO(img_res.content), media_type="image/png")

        except Exception as e:
            print(f"[Demask] CodeFormer failed ({e}); returning Step 1 result.")
            async with httpx.AsyncClient() as hc:
                img_res = await hc.get(inpainted_url)
            return StreamingResponse(BytesIO(img_res.content), media_type="image/png")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Demask] Unhandled error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# IOPaint Integration (Corrected)
# ==============================
import asyncio
import subprocess
import sys
from typing import Optional

import psutil
from fastapi import Request
from fastapi.responses import JSONResponse

# IOPaint process tracking
iopaint_process: Optional[subprocess.Popen] = None


@app.get("/sh-api/iopaint/status")
async def iopaint_status():
    """Check if IOPaint server is running"""
    global iopaint_process

    # Check if our tracked process is running
    if iopaint_process and iopaint_process.poll() is None:
        # Try to determine port from process arguments
        port = 8080  # default
        if iopaint_process.args:
            for arg in iopaint_process.args:
                if isinstance(arg, str) and "--port" in arg:
                    try:
                        if "=" in arg:
                            port = int(arg.split("=")[1].strip("\"' "))
                        elif iopaint_process.args.index(arg) + 1 < len(
                            iopaint_process.args
                        ):
                            port = int(
                                iopaint_process.args[
                                    iopaint_process.args.index(arg) + 1
                                ]
                            )
                    except (ValueError, IndexError):
                        pass
        return JSONResponse({"running": True, "port": port})

    # Also check if any python process is running on typical IOPaint ports
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
            if any("iopaint" in str(part).lower() for part in cmdline):
                port = 8080
                for i, arg in enumerate(cmdline):
                    if arg == "--port" and i + 1 < len(cmdline):
                        try:
                            port = int(cmdline[i + 1])
                        except (ValueError, IndexError):
                            pass
                    elif "--port=" in arg:
                        try:
                            port = int(arg.split("=")[1])
                        except (ValueError, IndexError):
                            pass
                return JSONResponse({"running": True, "port": port})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return JSONResponse({"running": False})


@app.post("/sh-api/iopaint/start")
async def iopaint_start(request: Request):
    """Start IOPaint server"""
    global iopaint_process

    if iopaint_process and iopaint_process.poll() is None:
        return JSONResponse({"success": False, "error": "IOPaint is already running"})

    try:
        data = await request.json()
        model = data.get("model", "lama")
        device = data.get("device", "cpu")
        port = data.get("port", 8080)

        # First check if iopaint is installed
        try:
            subprocess.run(
                [sys.executable, "-c", "import iopaint"],
                check=True,
                capture_output=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return JSONResponse(
                {
                    "success": False,
                    "error": "IOPaint is not installed. Install with: pip install iopaint",
                }
            )

        # Build the command - CORRECTED: use "iopaint start" not "iopaint.run web"
        iopaint_cmd = [
            sys.executable,
            "-m",
            "iopaint",
            "start",
            "--model",
            model,
            "--device",
            device,
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ]

        print(f"[IOPaint] Starting with command: {' '.join(iopaint_cmd)}")

        # Start IOPaint in the background
        iopaint_process = subprocess.Popen(
            iopaint_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Log process output asynchronously
        async def log_output():
            while iopaint_process and iopaint_process.poll() is None:
                try:
                    line = await asyncio.to_thread(iopaint_process.stdout.readline)
                    if line:
                        print(f"[IOPaint] {line.strip()}")
                except Exception as e:
                    print(f"[IOPaint Log Error] {e}")
                    break

        asyncio.create_task(log_output())

        # Wait a moment to see if process starts successfully
        await asyncio.sleep(2)

        if iopaint_process.poll() is not None:
            # Process died immediately
            stdout, stderr = "", ""
            try:
                stdout, stderr = iopaint_process.communicate(timeout=1)
            except:
                pass
            error_msg = stderr or stdout or "Process terminated immediately"
            iopaint_process = None
            return JSONResponse(
                {
                    "success": False,
                    "error": f"IOPaint failed to start: {error_msg[:200]}",
                }
            )

        return JSONResponse({"success": True, "port": port})
    except Exception as e:
        print(f"[IOPaint Start Error] {e}")
        if iopaint_process:
            try:
                iopaint_process.terminate()
                iopaint_process.wait(timeout=2)
            except:
                pass
            iopaint_process = None
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/sh-api/iopaint/stop")
async def iopaint_stop():
    """Stop IOPaint server"""
    global iopaint_process

    if iopaint_process:
        try:
            # Kill the process tree
            try:
                parent = psutil.Process(iopaint_process.pid)
                children = parent.children(recursive=True)

                for child in children:
                    try:
                        child.terminate()
                    except:
                        pass

                try:
                    parent.terminate()
                except:
                    pass

                # Wait for processes to terminate
                gone, alive = psutil.wait_procs([parent] + children, timeout=3)
                for p in alive:
                    try:
                        p.kill()
                    except:
                        pass
            except Exception:
                # Fallback to simple termination
                iopaint_process.terminate()
                try:
                    iopaint_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    iopaint_process.kill()

            iopaint_process = None
            return JSONResponse({"success": True})
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)})

    # Also try to find and kill any other iopaint processes
    killed = False
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
            if any("iopaint" in str(part).lower() for part in cmdline):
                try:
                    proc.terminate()
                    killed = True
                except:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return JSONResponse(
        {"success": killed, "error": None if killed else "No IOPaint process found"}
    )


@app.get("/sh-api/iopaint/devices")
async def iopaint_devices():
    """Detect available devices for IOPaint"""
    try:
        import torch

        devices = {
            "cuda": torch.cuda.is_available(),
            "mps": hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()
            and torch.backends.mps.is_built(),
        }
        return JSONResponse(devices)
    except ImportError:
        return JSONResponse({"cuda": False, "mps": False})
    except Exception as e:
        return JSONResponse({"cuda": False, "mps": False, "error": str(e)})


@app.get("/sh-api/iopaint/check")
async def iopaint_check():
    """Check if IOPaint is installed"""
    try:
        import iopaint

        # Try to get version in a safe way
        version = getattr(iopaint, "__version__", "unknown")
        return JSONResponse({"installed": True, "version": version})
    except ImportError:
        return JSONResponse({"installed": False})


# ==============================
# DeepMosaic Integration
# ==============================

# Replace the DeepMosaicService class in main.py with this updated version:


# Updated DeepMosaicService class for main.py
# Updated DeepMosaicService class with correct path handling
class DeepMosaicService:
    def __init__(self, deepmosaic_path: str = None):
        # First, try to find the DeepMosaic directory
        possible_dirs = [
            APP_ROOT / "DeepMosaics",
            APP_ROOT / "../DeepMosaics",
            Path("DeepMosaics"),
            Path("../DeepMosaics"),
        ]

        deepmosaic_dir = None
        for dir_path in possible_dirs:
            dir_path = dir_path.resolve()
            if dir_path.exists() and (dir_path / "deepmosaic.py").exists():
                deepmosaic_dir = dir_path
                break

        if not deepmosaic_dir:
            raise FileNotFoundError(
                "DeepMosaic directory not found. Expected: Social-Hunt/DeepMosaics/"
            )

        # Set the deepmosaic.py path
        deepmosaic_path = deepmosaic_dir / "deepmosaic.py"

        if not deepmosaic_path.exists():
            raise FileNotFoundError(f"deepmosaic.py not found at: {deepmosaic_path}")

        self.deepmosaic_path = str(deepmosaic_path)
        self.deepmosaic_dir = deepmosaic_dir
        self.results_dir = APP_ROOT / "data" / "deepmosaic_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        print(f"[INFO] DeepMosaic directory: {self.deepmosaic_dir}")
        print(f"[INFO] DeepMosaic script: {self.deepmosaic_path}")

        self.apply_compat_patches()

        # Check for models
        self.check_models()

    def check_models(self):
        """Check if models exist and provide guidance"""
        models_dir = self.deepmosaic_dir / "pretrained_models"

        if not models_dir.exists():
            print(f"[WARN] Models directory not found: {models_dir}")
            print("[INFO] Creating symlink to models in Social-Hunt root...")

            root_models = APP_ROOT / "pretrained_models"
            if root_models.exists():
                try:
                    models_dir.symlink_to(root_models, target_is_directory=True)
                    print(f"[INFO] Created symlink: {models_dir} -> {root_models}")
                except Exception as e:
                    print(f"[ERROR] Failed to create symlink: {e}")
                    print(
                        f"[INFO] You can manually create it: ln -s ../pretrained_models {models_dir}"
                    )
            else:
                print("[ERROR] No models found in Social-Hunt root either!")
                print("[INFO] Please download models and place them in either:")
                print(f"[INFO]   1. {models_dir}")
                print(f"[INFO]   2. {APP_ROOT / 'pretrained_models'}")
                print("[INFO] Download from: https://github.com/HypoX64/DeepMosaics")

        # Check for essential models
        essential_models = [
            models_dir / "mosaic" / "clean_youknow_v1.pth",
            models_dir / "mosaic" / "add_face.pth",
            models_dir / "style" / "style_monet.pth",
        ]

        for model in essential_models:
            if not model.exists():
                print(f"[WARN] Missing model: {model}")

    def apply_compat_patches(self) -> None:
        """Patch DeepMosaics for newer PyTorch/InstanceNorm behavior."""
        updated = False
        model_util_path = self.deepmosaic_dir / "models" / "model_util.py"
        loadmodel_path = self.deepmosaic_dir / "models" / "loadmodel.py"

        if model_util_path.exists():
            try:
                text = model_util_path.read_text(encoding="utf-8", errors="ignore")
                patch_block = """# patch InstanceNorm checkpoints prior to 0.4
def patch_instance_norm_state_dict(state_dict, module, keys, i=0):
    \"\"\"Fix InstanceNorm checkpoints incompatibility (prior to 0.4)\"\"\"
    key = keys[i]
    if i + 1 == len(keys):  # at the end, pointing to a parameter/buffer
        if module.__class__.__name__.startswith('InstanceNorm') and \\
                (key == 'running_mean' or key == 'running_var'):
            if getattr(module, key) is None:
                state_dict.pop('.'.join(keys))
        if module.__class__.__name__.startswith('InstanceNorm') and \\
           (key == 'num_batches_tracked'):
            state_dict.pop('.'.join(keys))
    else:
        if hasattr(module, key):
            patch_instance_norm_state_dict(state_dict, getattr(module, key), keys, i + 1)
        else:
            state_dict.pop('.'.join(keys), None)
"""
                pattern = (
                    r"# patch InstanceNorm checkpoints prior to 0.4\\n"
                    r"def patch_instance_norm_state_dict[\\s\\S]*?\\n"
                    r"################################## initialization"
                )
                new_text = re.sub(
                    pattern,
                    patch_block + "\n################################## initialization",
                    text,
                    count=1,
                )
                if new_text != text:
                    model_util_path.write_text(new_text, encoding="utf-8")
                    updated = True
            except Exception as e:
                print(f"[WARN] Failed to patch DeepMosaics model_util.py: {e}")

        if loadmodel_path.exists():
            try:
                text = loadmodel_path.read_text(encoding="utf-8", errors="ignore")
                if "netG.load_state_dict(state_dict, strict=False)" not in text:
                    if "netG.load_state_dict(state_dict)" in text:
                        text = text.replace(
                            "netG.load_state_dict(state_dict)",
                            "netG.load_state_dict(state_dict, strict=False)",
                            1,
                        )
                        loadmodel_path.write_text(text, encoding="utf-8")
                        updated = True
            except Exception as e:
                print(f"[WARN] Failed to patch DeepMosaics loadmodel.py: {e}")

        if updated:
            print("[INFO] Applied DeepMosaics compatibility patches")

    async def process_image(
        self,
        input_path: str,
        mode: str = "clean",
        mosaic_type: str = "squa_avg",
        quality: str = "medium",
        output_format: str = "png",
    ) -> Dict[str, Any]:
        """Process a single image with DeepMosaic"""
        try:
            # Generate unique output filename
            job_id = str(uuid.uuid4())
            output_dir = self.results_dir / job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # Convert input_path to absolute path
            input_path = Path(input_path).resolve()

            print(f"[DeepMosaic] Processing: {input_path}")
            print(f"[DeepMosaic] Mode: {mode}, Quality: {quality}")

            # Build command - START WITH BASIC PARAMETERS
            cmd = [
                sys.executable,
                "-u",
                "deepmosaic.py",
                "--media_path",
                str(input_path),
                "--mode",
                mode,
                "--result_dir",
                str(output_dir),
                "--temp_dir",
                str(output_dir / "temp"),
                "--no_preview",
            ]

            # Add mode-specific parameters CORRECTLY
            if mode == "add":
                # For add mode, we need model and mosaic type
                add_model = (
                    self.deepmosaic_dir
                    / "pretrained_models"
                    / "mosaic"
                    / "add_face.pth"
                )
                if add_model.exists():
                    cmd.extend(["--model_path", str(add_model)])

                cmd.extend(["--mosaic_mod", mosaic_type])

                # Adjust quality settings for add mode
                if quality == "high":
                    cmd.extend(["--mask_extend", "5"])  # More precise
                elif quality == "low":
                    cmd.extend(["--mask_extend", "20"])  # Faster
                else:  # medium
                    cmd.extend(["--mask_extend", "10"])

            elif mode == "clean":
                # For clean mode, we need the clean model
                # Try different clean models
                clean_models = [
                    self.deepmosaic_dir
                    / "pretrained_models"
                    / "mosaic"
                    / "clean_face_HD.pth",
                    self.deepmosaic_dir
                    / "pretrained_models"
                    / "mosaic"
                    / "clean_youknow_v1.pth",
                ]

                for model in clean_models:
                    if model.exists():
                        cmd.extend(["--model_path", str(model)])
                        break

                # ONLY add traditional parameters if user explicitly chooses "traditional" quality
                # But wait - traditional is a separate option, not quality!
                # Actually, looking at DeepMosaic docs:
                # --traditional: if specified, use traditional image processing methods to clean mosaic
                # So we should only add --traditional if quality == "traditional"

                # Let's map quality to DeepMosaic parameters differently:
                if quality == "traditional":
                    # Use traditional method (non-AI)
                    cmd.extend(["--traditional"])
                    # Add traditional parameters based on quality "level"
                    cmd.extend(["--tr_blur", "10", "--tr_down", "10"])
                # else: use AI model (default)

            elif mode == "style":
                # For style transfer
                style_model = (
                    self.deepmosaic_dir / "pretrained_models" / "style" / "candy.pth"
                )
                if style_model.exists():
                    cmd.extend(["--model_path", str(style_model)])

                if quality == "high":
                    cmd.extend(["--output_size", "1024"])
                elif quality == "low":
                    cmd.extend(["--output_size", "256"])
                else:  # medium
                    cmd.extend(["--output_size", "512"])

            # Add GPU if available (optional)
            # cmd.extend(["--gpu_id", "0"])  # Uncomment if you have GPU

            print(f"[DeepMosaic] Command: {' '.join(cmd)}")
            print(f"[DeepMosaic] Working directory: {self.deepmosaic_dir}")

            # Run DeepMosaic
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=str(self.deepmosaic_dir),
            )

            # Rest of the function remains the same...

            # Set timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=300
                )
            except asyncio.TimeoutError:
                print("[DeepMosaic] Timeout, terminating...")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                raise Exception("Processing timeout (5 minutes)")

            stdout_str = stdout.decode("utf-8", errors="ignore")
            stderr_str = stderr.decode("utf-8", errors="ignore")

            print(f"[DeepMosaic] Exit code: {process.returncode}")

            if process.returncode != 0:
                error_msg = stderr_str or stdout_str or "Unknown error"
                if "Model does not exist" in error_msg:
                    raise Exception(
                        f"Models missing. Check {self.deepmosaic_dir / 'pretrained_models'}"
                    )
                raise Exception(f"DeepMosaic error: {error_msg[:500]}")

            # Find output
            output_files = list(output_dir.glob("*"))
            output_files = [f for f in output_files if f.is_file()]

            if output_files:
                output_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                output_path = output_files[0]

                print(f"[DeepMosaic] Output: {output_path}")

                return {
                    "success": True,
                    "job_id": job_id,
                    "output_path": str(output_path),
                    "stdout": stdout_str[:1000],  # Limit size
                    "stderr": stderr_str[:1000],
                }
            else:
                raise Exception("No output file generated")

        except Exception as e:
            print(f"[DeepMosaic Error] {e}")
            return {"success": False, "error": str(e)}


# Initialize DeepMosaic service
try:
    deepmosaic_service = DeepMosaicService("DeepMosaics/deepmosaic.py")
    print("[INFO] DeepMosaic service initialized successfully")
except Exception as e:
    print(f"[WARN] Failed to initialize DeepMosaic: {e}")
    deepmosaic_service = None


# DeepMosaic API endpoints
@app.get("/sh-api/deepmosaic/status")
async def api_deepmosaic_status():
    """Check DeepMosaic availability"""
    return {
        "available": deepmosaic_service is not None,
        "message": "DeepMosaic ready"
        if deepmosaic_service
        else "DeepMosaic not available",
        "details": {
            "service_initialized": deepmosaic_service is not None,
            "module_path": deepmosaic_service.deepmosaic_path
            if deepmosaic_service
            else None,
        },
    }


@app.post("/sh-api/deepmosaic/process")
async def api_deepmosaic_process(
    file: UploadFile = File(...),
    mode: str = Form("clean"),
    mosaic_type: str = Form("squa_avg"),
    quality: str = Form("medium"),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Process image/video with DeepMosaic
    """
    require_admin(x_plugin_token)

    if not deepmosaic_service:
        raise HTTPException(status_code=500, detail="DeepMosaic service not available")

    # Save uploaded file
    temp_dir = Path("temp/deepmosaic")
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_filename = _safe_name(file.filename or "upload")
    input_path = temp_dir / safe_filename
    content = await file.read()
    input_path.write_bytes(content)

    print(
        f"[DeepMosaic] Processing file: {safe_filename}, size: {len(content)} bytes, mode: {mode}"
    )

    # Determine if it's an image or video
    file_ext = input_path.suffix.lower()
    is_video = file_ext in [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"]

    try:
        if is_video:
            print(f"[DeepMosaic] Processing as video: {safe_filename}")
            result = await deepmosaic_service.process_video(
                input_path=str(input_path),
                mode=mode,
                mosaic_type=mosaic_type,
                quality=quality,
            )
        else:
            print(f"[DeepMosaic] Processing as image: {safe_filename}")
            result = await deepmosaic_service.process_image(
                input_path=str(input_path),
                mode=mode,
                mosaic_type=mosaic_type,
                quality=quality,
            )

        if not result.get("success"):
            error_msg = result.get("error", "Unknown error")
            print(f"[DeepMosaic] Processing failed: {error_msg}")
            raise HTTPException(
                status_code=500, detail=f"DeepMosaic processing failed: {error_msg}"
            )

        # Return the processed file
        output_path = Path(result["output_path"])
        if output_path.exists():
            print(f"[DeepMosaic] Returning result file: {output_path}")

            # Determine content type
            if is_video:
                media_type = "video/mp4"
                if output_path.suffix.lower() == ".avi":
                    media_type = "video/x-msvideo"
                elif output_path.suffix.lower() == ".mov":
                    media_type = "video/quicktime"
                elif output_path.suffix.lower() == ".webm":
                    media_type = "video/webm"
            else:
                media_type = "image/png"
                if output_path.suffix.lower() in [".jpg", ".jpeg"]:
                    media_type = "image/jpeg"
                elif output_path.suffix.lower() == ".bmp":
                    media_type = "image/bmp"
                elif output_path.suffix.lower() == ".tiff":
                    media_type = "image/tiff"
                elif output_path.suffix.lower() == ".webp":
                    media_type = "image/webp"

            return FileResponse(
                path=output_path,
                media_type=media_type,
                filename=f"deepmosaic_{mode}_{safe_filename}",
                headers={
                    "X-Job-ID": result.get("job_id", ""),
                    "X-Output-Path": str(output_path),
                },
            )
        else:
            print(f"[DeepMosaic] Output file not found: {output_path}")
            raise HTTPException(status_code=500, detail="Output file not found")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DeepMosaic] Unhandled exception: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Cleanup temp file
        try:
            if input_path.exists():
                input_path.unlink()
                print(f"[DeepMosaic] Cleaned up temp file: {input_path}")
        except Exception as e:
            print(f"[DeepMosaic] Failed to cleanup temp file: {e}")


@app.get("/sh-api/deepmosaic/jobs/{job_id}/download")
async def api_deepmosaic_download(
    job_id: str,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Download a previously processed DeepMosaic result
    """
    require_admin(x_plugin_token)

    if not deepmosaic_service:
        raise HTTPException(status_code=500, detail="DeepMosaic service not available")

    # Check if job result exists in the results directory
    result_path = deepmosaic_service.results_dir / job_id

    if result_path.is_dir():
        # Look for files in the job directory
        files = list(result_path.glob("*"))
        # Filter out directories and hidden files
        files = [f for f in files if f.is_file() and not f.name.startswith(".")]

        if files:
            # Find the largest file (likely the main output)
            files.sort(key=lambda f: f.stat().st_size, reverse=True)
            output_file = files[0]

            # Determine content type
            if output_file.suffix.lower() in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
                media_type = "video/mp4"
                if output_file.suffix.lower() == ".avi":
                    media_type = "video/x-msvideo"
                elif output_file.suffix.lower() == ".mov":
                    media_type = "video/quicktime"
                elif output_file.suffix.lower() == ".webm":
                    media_type = "video/webm"
            else:
                media_type = "image/png"
                if output_file.suffix.lower() in [".jpg", ".jpeg"]:
                    media_type = "image/jpeg"
                elif output_file.suffix.lower() == ".bmp":
                    media_type = "image/bmp"
                elif output_file.suffix.lower() == ".tiff":
                    media_type = "image/tiff"
                elif output_file.suffix.lower() == ".webp":
                    media_type = "image/webp"

            return FileResponse(
                path=output_file,
                media_type=media_type,
                filename=f"deepmosaic_{job_id}{output_file.suffix}",
            )

    # Also check for direct file (for older jobs)
    possible_files = [
        deepmosaic_service.results_dir / f"{job_id}.png",
        deepmosaic_service.results_dir / f"{job_id}.jpg",
        deepmosaic_service.results_dir / f"{job_id}.mp4",
        deepmosaic_service.results_dir / f"{job_id}.avi",
    ]

    for file_path in possible_files:
        if file_path.exists():
            # Determine content type
            if file_path.suffix.lower() in [".mp4", ".avi"]:
                media_type = (
                    "video/mp4"
                    if file_path.suffix.lower() == ".mp4"
                    else "video/x-msvideo"
                )
            else:
                media_type = (
                    "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
                )

            return FileResponse(
                path=file_path, media_type=media_type, filename=file_path.name
            )

    raise HTTPException(status_code=404, detail="Job result not found")


@app.get("/sh-api/deepmosaic/jobs/{job_id}/info")
async def api_deepmosaic_job_info(
    job_id: str,
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    Get information about a DeepMosaic job
    """
    require_admin(x_plugin_token)

    if not deepmosaic_service:
        raise HTTPException(status_code=500, detail="DeepMosaic service not available")

    result_path = deepmosaic_service.results_dir / job_id

    info = {"job_id": job_id, "exists": False, "is_directory": False, "files": []}

    if result_path.exists():
        info["exists"] = True
        info["is_directory"] = result_path.is_dir()

        if result_path.is_dir():
            files = list(result_path.glob("*"))
            info["files"] = [
                {
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                    "is_file": f.is_file(),
                }
                for f in files
            ]
        else:
            info["files"] = [
                {
                    "name": result_path.name,
                    "size": result_path.stat().st_size,
                    "modified": result_path.stat().st_mtime,
                    "is_file": True,
                }
            ]

    return info


# ---------------------------
# UI
# ---------------------------
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/")
async def root():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.post("/sh-api/auth/verify")
async def api_auth_verify(
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    require_admin(x_plugin_token)
    return {"ok": True}


@app.get("/sh-api/public/theme")
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
