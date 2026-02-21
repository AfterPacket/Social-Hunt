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
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
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
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Disable caching for all responses to ensure users always see the latest UI and data
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Security headers (address OWASP ZAP findings)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://js.hcaptcha.com; "
        "style-src 'self' 'unsafe-inline' https://newassets.hcaptcha.com; "
        "img-src 'self' data: blob: https://newassets.hcaptcha.com; "
        "connect-src 'self' https://hcaptcha.com https://newassets.hcaptcha.com; "
        "frame-src 'self' https://newassets.hcaptcha.com; "
        "font-src 'self' data:; "
        "form-action 'self'; "
        "frame-ancestors 'self';"
    )
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


# ---- login rate limiter ----
import threading as _threading


def _captcha_active() -> bool:
    """Returns True when hCaptcha is configured (both env vars present)."""
    return bool((os.getenv("HCAPTCHA_SECRET") or "").strip())


class _LoginRateLimiter:
    """
    Per-IP brute-force protection for the auth/verify endpoint.

    Limits are tightened automatically when hCaptcha is active (bots are
    blocked at the captcha layer so 5 attempts is plenty).  When captcha is
    not configured the limits are relaxed so a human mistyping their own
    token cannot easily lock themselves out.

    With captcha   : 5 failures / 60 s window → 5-minute lockout
    Without captcha: 20 failures / 600 s window → 60-second lockout
    """

    def __init__(self):
        self._lock = _threading.Lock()
        self._records: Dict[str, Any] = {}

    @staticmethod
    def _limits():
        if _captcha_active():
            return 5, 60, 300      # max_failures, window_sec, lockout_sec
        return 20, 600, 60         # relaxed — human-friendly

    def _rec(self, ip: str) -> Dict:
        return self._records.setdefault(
            ip,
            {"failures": 0, "window_start": time.monotonic(), "locked_until": 0.0},
        )

    def is_locked(self, ip: str) -> bool:
        max_failures, window_sec, _ = self._limits()
        with self._lock:
            rec = self._rec(ip)
            now = time.monotonic()
            if now < rec["locked_until"]:
                return True
            if now - rec["window_start"] > window_sec:
                rec["failures"] = 0
                rec["window_start"] = now
            return False

    def record_failure(self, ip: str) -> int:
        """Record a failed attempt. Returns remaining attempts before lockout."""
        max_failures, window_sec, lockout_sec = self._limits()
        with self._lock:
            rec = self._rec(ip)
            now = time.monotonic()
            if now - rec["window_start"] > window_sec:
                rec["failures"] = 0
                rec["window_start"] = now
            rec["failures"] += 1
            remaining = max(0, max_failures - rec["failures"])
            if rec["failures"] >= max_failures:
                rec["locked_until"] = now + lockout_sec
            return remaining

    def record_success(self, ip: str) -> None:
        with self._lock:
            self._records.pop(ip, None)


_login_limiter = _LoginRateLimiter()


async def _verify_hcaptcha(token: str) -> bool:
    """Verify hCaptcha response server-side. Returns True if disabled or valid."""
    secret = (os.getenv("HCAPTCHA_SECRET") or "").strip()
    if not secret:
        return True  # CAPTCHA not configured — skip
    if not token:
        return False
    try:
        async with httpx.AsyncClient(trust_env=False) as c:
            r = await c.post(
                "https://api.hcaptcha.com/siteverify",
                data={"secret": secret, "response": token},
                timeout=5,
            )
        return r.json().get("success", False)
    except Exception:
        return True  # fail open on network error


class AuthVerifyReq(BaseModel):
    hcaptcha_token: Optional[str] = None


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


def _detect_gender_hint(
    image_bytes: bytes,
    face_boxes: list,
) -> str:
    """
    Analyse the eyebrow strip (25–40 % of face height) to infer gender.
    Male eyebrows are typically darker, thicker, and have a higher dark-pixel
    density relative to the surrounding skin.  Female eyebrows tend to be
    thinner with a higher arch and a lower density.

    Returns: "man", "woman", or "unknown"
    """
    from PIL import Image as PILImage

    def _lum(r, g, b):
        return r * 0.299 + g * 0.587 + b * 0.114

    try:
        pil = PILImage.open(BytesIO(image_bytes)).convert("RGB")

        fore_lums: list[float] = []
        brow_dark_ratios: list[float] = []

        for top, right, bottom, left in face_boxes:
            fh = bottom - top
            fw = right - left
            if fh < 40 or fw < 40:
                continue

            # Skin baseline: top 20 % of face box
            ft, fb = top, top + max(1, int(fh * 0.20))
            fl, fr = left + int(fw * 0.25), right - int(fw * 0.25)
            if fb > ft and fr > fl:
                crop = pil.crop((fl, ft, fr, fb))
                fore_lums.extend(_lum(*p) for p in crop.getdata())

            # Eyebrow strip: 25–40 % of face height
            et = top + int(fh * 0.25)
            eb = top + int(fh * 0.40)
            el = left + int(fw * 0.10)
            er = right - int(fw * 0.10)
            if eb > et and er > el and fore_lums:
                avg_fore = sum(fore_lums) / len(fore_lums)
                brow_crop = pil.crop((el, et, er, eb))
                pixels = list(brow_crop.getdata())
                if pixels:
                    # Ratio of pixels darker than 55 % of forehead luminance
                    threshold = avg_fore * 0.55
                    dark_ratio = sum(1 for p in pixels if _lum(*p) < threshold) / len(
                        pixels
                    )
                    brow_dark_ratios.append(dark_ratio)

        if not brow_dark_ratios:
            return "unknown"

        avg_ratio = sum(brow_dark_ratios) / len(brow_dark_ratios)
        print(f"[Demask] Gender hint: eyebrow dark-pixel ratio={avg_ratio:.3f}")

        # Empirically: male brow ratio tends to be > 0.20, female < 0.14
        if avg_ratio > 0.20:
            return "man"
        elif avg_ratio < 0.13:
            return "woman"
        else:
            return "unknown"

    except Exception as e:
        print(f"[Demask] Gender detection failed ({e}); using unknown.")
        return "unknown"


def _prefill_mask_with_skin(
    image_bytes: bytes,
    mask_bytes: bytes,
    face_boxes: list,
) -> bytes:
    """
    Before handing the image to SD inpainting, fill the masked (gaiter/balaclava)
    region with the subject's approximate skin colour sampled from the forehead.

    Why: SD inpainting sees the white gaiter and associates it with a face
    covering, so it generates a replacement mask (surgical mask etc.) instead
    of facial features.  By painting the covered region with skin colour first,
    the model is presented with a flesh-coloured blank and generates actual
    face anatomy rather than another mask.
    """
    from PIL import Image as PILImage

    try:
        original = PILImage.open(BytesIO(image_bytes)).convert("RGB")
        mask_pil = PILImage.open(BytesIO(mask_bytes)).convert("L")
        w, h = original.size

        # Sample forehead for skin colour
        skin_r, skin_g, skin_b = 200, 170, 150  # neutral fallback
        for top, right, bottom, left in face_boxes:
            fh = bottom - top
            fw = right - left
            ft = top
            fb = top + max(1, int(fh * 0.20))
            fl = left + int(fw * 0.25)
            fr = right - int(fw * 0.25)
            if fb > ft and fr > fl:
                crop = original.crop((fl, ft, fr, fb))
                pixels = list(crop.getdata())
                if pixels:
                    skin_r = sum(p[0] for p in pixels) // len(pixels)
                    skin_g = sum(p[1] for p in pixels) // len(pixels)
                    skin_b = sum(p[2] for p in pixels) // len(pixels)
                break

        # Fill mask region with skin colour
        skin_fill = PILImage.new("RGB", (w, h), (skin_r, skin_g, skin_b))
        prefilled = PILImage.composite(skin_fill, original, mask_pil)

        buf = BytesIO()
        prefilled.save(buf, format="PNG")
        print(
            f"[Demask] Pre-filled mask region with skin colour "
            f"rgb({skin_r},{skin_g},{skin_b})."
        )
        return buf.getvalue()

    except Exception as e:
        print(f"[Demask] Skin pre-fill failed ({e}); using original image.")
        return image_bytes


def _sample_skin_tone(
    image_bytes: bytes,
    face_boxes: list,
) -> str:
    """
    Sample pixels from the forehead region (above the covered area) to derive
    a rough skin-tone description that can be injected into the inpainting
    prompt. This anchors the model to the subject's actual complexion so it
    does not generate a face with the wrong ethnicity.
    """
    from PIL import Image as PILImage

    try:
        pil = PILImage.open(BytesIO(image_bytes)).convert("RGB")
        w_img, h_img = pil.size

        samples: list[tuple[int, int, int]] = []

        for top, right, bottom, left in face_boxes:
            fh = bottom - top
            fw = right - left
            # Forehead strip: top 20 % of the face box, centre 50 % horizontally
            fore_top = top
            fore_bot = top + max(1, int(fh * 0.20))
            fore_left = left + int(fw * 0.25)
            fore_right = right - int(fw * 0.25)
            if fore_bot <= fore_top or fore_right <= fore_left:
                continue
            crop = pil.crop((fore_left, fore_top, fore_right, fore_bot))
            samples.extend(list(crop.getdata()))

            # Also sample neck region just below the face box
            neck_top = bottom + int(fh * 0.05)
            neck_bot = min(h_img, bottom + int(fh * 0.25))
            if neck_bot > neck_top:
                neck_crop = pil.crop((fore_left, neck_top, fore_right, neck_bot))
                samples.extend(list(neck_crop.getdata()))

        if not samples:
            return "natural skin tone"

        avg_r = sum(p[0] for p in samples) // len(samples)
        avg_g = sum(p[1] for p in samples) // len(samples)
        avg_b = sum(p[2] for p in samples) // len(samples)

        # Rough ITA (Individual Typology Angle) approximation to classify tone
        if avg_r > 210 and avg_g > 180:
            return "very fair caucasian skin, light complexion, pale skin"
        elif avg_r > 185 and avg_g > 150:
            return "fair caucasian skin, light skin tone"
        elif avg_r > 160 and avg_g > 120:
            return "medium skin tone, light-medium complexion"
        elif avg_r > 130 and avg_g > 90:
            return "olive or tan skin tone, medium-dark complexion"
        elif avg_r > 100:
            return "dark skin tone, brown complexion"
        else:
            return "very dark skin tone, deep brown complexion"

    except Exception as e:
        print(f"[Demask] Skin tone sampling failed ({e}); using generic hint.")
        return "natural skin tone"


def _detect_facial_hair(
    image_bytes: bytes,
    face_boxes: list,
) -> str:
    """
    Analyse the visible jaw/cheek sides (the strip between the eyes and where
    the gaiter begins) to determine whether facial hair is present.

    Strategy:
      - Forehead brightness   → baseline clean-skin luminance
      - Jaw-side brightness   → sample the outer edges of the face just above
                                the mask line (50 % of face height) where the
                                sides of the jaw are often still exposed
      - If the jaw area is significantly darker than the forehead the contrast
        is characteristic of beard/stubble shadow → return "has_facial_hair"
      - If similar luminance  → return "clean_shaven"
      - If we cannot get enough pixels → return "unknown" (prompt stays neutral)

    Luminance is computed as (R*0.299 + G*0.587 + B*0.114) to match human
    perception; hair shows up as a drop in luminance rather than just red.
    """
    from PIL import Image as PILImage

    def _lum(r, g, b):
        return r * 0.299 + g * 0.587 + b * 0.114

    try:
        pil = PILImage.open(BytesIO(image_bytes)).convert("RGB")
        w_img, h_img = pil.size

        fore_lums: list[float] = []
        jaw_lums: list[float] = []

        for top, right, bottom, left in face_boxes:
            fh = bottom - top
            fw = right - left

            if fh < 40 or fw < 40:
                continue

            # ── Forehead baseline (top 20 %, centre 40 % width) ───────────────
            ft = top
            fb = top + max(1, int(fh * 0.20))
            fl = left + int(fw * 0.30)
            fr = right - int(fw * 0.30)
            if fb > ft and fr > fl:
                crop = pil.crop((fl, ft, fr, fb))
                fore_lums.extend(_lum(*p) for p in crop.getdata())

            # ── Jaw/cheek sides — outer 15 % of width, 40–55 % of height ─────
            # This strip sits between the eyes and the gaiter line and is the
            # region most likely to show stubble shadow even when masked.
            jt = top + int(fh * 0.40)
            jb = top + int(fh * 0.56)
            # Left strip
            jaw_left_r = min(w_img, left + int(fw * 0.15))
            if jb > jt and jaw_left_r > left:
                crop_l = pil.crop((left, jt, jaw_left_r, jb))
                jaw_lums.extend(_lum(*p) for p in crop_l.getdata())
            # Right strip
            jaw_right_l = max(0, right - int(fw * 0.15))
            if jb > jt and right > jaw_right_l:
                crop_r = pil.crop((jaw_right_l, jt, right, jb))
                jaw_lums.extend(_lum(*p) for p in crop_r.getdata())

        if len(fore_lums) < 20 or len(jaw_lums) < 10:
            print("[Demask] Facial hair detection: insufficient pixels → unknown")
            return "unknown"

        avg_fore = sum(fore_lums) / len(fore_lums)
        avg_jaw = sum(jaw_lums) / len(jaw_lums)
        drop = avg_fore - avg_jaw  # positive = jaw is darker than forehead

        print(
            f"[Demask] Facial hair: forehead_lum={avg_fore:.1f}, "
            f"jaw_lum={avg_jaw:.1f}, drop={drop:.1f}"
        )

        # A drop of ~18+ luminance units is characteristic of visible stubble
        # (light stubble ≈ 18–30, full beard ≈ 30+).
        # Values below 12 are within normal skin variation (no hair).
        if drop >= 30:
            return "has_facial_hair"  # clear beard/heavy stubble
        elif drop >= 18:
            return "likely_facial_hair"  # light stubble likely present
        elif drop >= 12:
            return "unknown"  # ambiguous — stay neutral
        else:
            return "clean_shaven"

    except Exception as e:
        print(f"[Demask] Facial hair detection failed ({e}); defaulting to unknown.")
        return "unknown"


def _generate_face_coverage_mask(image_bytes: bytes) -> tuple[bytes, list, bool]:
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
    face_boxes: list = []  # (top, right, bottom, left)

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
    used_heuristic = False
    if not face_boxes:
        print(
            "[Demask] No face detected (subject likely fully covered). "
            "Applying head-region heuristic mask."
        )
        used_heuristic = True
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

        # Cover from ~50 % below the top of the face box (nose-bridge line) down
        # to just below the chin.  Starting at 50 % avoids masking the eyes and
        # upper nose, which are the strongest identity anchors — leaving them
        # visible constrains the model and reduces hallucinated features.
        pad_x = int(fw * 0.10)
        mask_top = top + int(fh * 0.50)
        mask_bottom = min(h_img, bottom + int(fh * 0.06))
        mask_left = max(0, left - pad_x)
        mask_right = min(w_img, right + pad_x)

        draw.rectangle([mask_left, mask_top, mask_right, mask_bottom], fill=255)

    # Feather edges so the inpainted region blends naturally at boundaries
    mask = mask.filter(ImageFilter.GaussianBlur(radius=6))
    mask = mask.point(lambda p: 255 if p > 25 else 0)

    buf = BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue(), face_boxes, used_heuristic


def _detect_gender_from_body(image_bytes: bytes) -> str:
    """
    Estimate gender from visible upper-body cues when the face is fully covered
    and the eyebrow-based heuristic cannot be trusted.

    Strategy: compare shoulder width (sampled at ~35–45 % image height) against
    the waist/lower-torso width (sampled at ~65–75 % image height).  Male bodies
    typically have shoulders wider than or equal to the hips; female bodies tend
    to narrow more at the waist relative to the shoulders.

    We also look at the average colour saturation in both strips — high-contrast
    tactical/military gear (low saturation, dark tones) is a weak but useful cue.

    Returns: "man", "woman", or "unknown"
    """
    from PIL import Image as PILImage

    try:
        pil = PILImage.open(BytesIO(image_bytes)).convert("RGB")
        w_img, h_img = pil.size

        # ── shoulder strip: 35–45 % of image height, centre 80 % of width ──
        sh_top = int(h_img * 0.35)
        sh_bot = int(h_img * 0.45)
        sh_left = int(w_img * 0.10)
        sh_right = int(w_img * 0.90)
        if sh_bot <= sh_top or sh_right <= sh_left:
            return "unknown"

        shoulder_crop = pil.crop((sh_left, sh_top, sh_right, sh_bot))
        sh_pixels = list(shoulder_crop.getdata())

        # ── waist/hip strip: 65–75 % of image height, centre 80 % of width ──
        wp_top = int(h_img * 0.65)
        wp_bot = int(h_img * 0.75)
        wp_left = int(w_img * 0.10)
        wp_right = int(w_img * 0.90)

        # Determine effective occupied width in each strip by finding the
        # outermost non-background pixels (significantly darker than the
        # image average brightness, which avoids false-positives from light bg).
        def _effective_width(pixels, strip_w, strip_h, threshold_lum=200):
            """Return fraction of strip width that contains non-background pixels."""
            if not pixels or strip_w <= 0 or strip_h <= 0:
                return 0.5
            # Build column luminance averages
            col_lums = []
            for col in range(strip_w):
                col_pix = [
                    pixels[row * strip_w + col]
                    for row in range(strip_h)
                    if row * strip_w + col < len(pixels)
                ]
                if col_pix:
                    avg_l = sum(
                        p[0] * 0.299 + p[1] * 0.587 + p[2] * 0.114 for p in col_pix
                    ) / len(col_pix)
                    col_lums.append(avg_l)
            # Count columns below the background threshold (non-background)
            occupied = sum(1 for l in col_lums if l < threshold_lum)
            return occupied / max(1, len(col_lums))

        sh_w = sh_right - sh_left
        sh_h = sh_bot - sh_top
        sh_frac = _effective_width(sh_pixels, sh_w, sh_h)

        wp_frac = 0.5  # default
        if wp_bot > wp_top and wp_right > wp_left:
            waist_crop = pil.crop((wp_left, wp_top, wp_right, wp_bot))
            wp_pixels = list(waist_crop.getdata())
            wp_frac = _effective_width(wp_pixels, wp_right - wp_left, wp_bot - wp_top)

        ratio = sh_frac / max(wp_frac, 0.01)
        print(
            f"[Demask] Body gender: shoulder_frac={sh_frac:.3f}, "
            f"waist_frac={wp_frac:.3f}, ratio={ratio:.3f}"
        )

        # Broader shoulders relative to waist → "man"
        # Male ratio typically ≥ 1.05; female ratio typically ≤ 0.97
        if ratio >= 1.05:
            return "man"
        elif ratio <= 0.95:
            return "woman"
        else:
            return "unknown"

    except Exception as e:
        print(f"[Demask] Body gender detection failed ({e}); returning unknown.")
        return "unknown"


def _crop_for_inpainting(
    image_bytes: bytes,
    mask_bytes: bytes,
    face_boxes: list,
) -> tuple:
    """
    Crop the face region (+ generous padding) from the full image and mask,
    resize both to 512×512 for SD inpainting, and return everything needed
    to composite the result back onto the original later.

    Returns:
        crop_img_b64  – base64 data-URI of the 512×512 crop
        crop_mask_b64 – base64 data-URI of the 512×512 mask crop
        crop_region   – (left, top, right, bottom) in original pixel coords
        orig_size     – (width, height) of the original image
        crop_size     – (width, height) of the un-resized crop
    """
    from PIL import Image as PILImage

    original = PILImage.open(BytesIO(image_bytes)).convert("RGB")
    mask_pil = PILImage.open(BytesIO(mask_bytes)).convert("L")
    orig_w, orig_h = original.size

    if not face_boxes:
        # No face box — send full image, caller composites normally
        b64_img = f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
        b64_msk = f"data:image/png;base64,{base64.b64encode(mask_bytes).decode()}"
        return (
            b64_img,
            b64_msk,
            (0, 0, orig_w, orig_h),
            (orig_w, orig_h),
            (orig_w, orig_h),
        )

    # Build a bounding box that encompasses all detected faces + 60 % padding
    tops = [b[0] for b in face_boxes]
    rights = [b[1] for b in face_boxes]
    bottoms = [b[2] for b in face_boxes]
    lefts = [b[3] for b in face_boxes]

    fh = min(bottoms) - max(tops)
    fw = max(rights) - min(lefts)
    pad = int(max(fh, fw) * 0.60)

    cl = max(0, min(lefts) - pad)
    ct = max(0, min(tops) - pad)
    cr = min(orig_w, max(rights) + pad)
    cb = min(orig_h, max(bottoms) + pad)

    # Enforce minimum 256 px on each axis
    if cr - cl < 256:
        extra = (256 - (cr - cl)) // 2
        cl = max(0, cl - extra)
        cr = min(orig_w, cr + extra)
    if cb - ct < 256:
        extra = (256 - (cb - ct)) // 2
        ct = max(0, ct - extra)
        cb = min(orig_h, cb + extra)

    crop_region = (cl, ct, cr, cb)
    crop_w, crop_h = cr - cl, cb - ct

    img_crop = original.crop(crop_region).resize((512, 512), PILImage.LANCZOS)
    mask_crop = mask_pil.crop(crop_region).resize((512, 512), PILImage.NEAREST)

    buf_i = BytesIO()
    img_crop.save(buf_i, format="PNG")
    buf_m = BytesIO()
    mask_crop.save(buf_m, format="PNG")

    b64_img = f"data:image/png;base64,{base64.b64encode(buf_i.getvalue()).decode()}"
    b64_msk = f"data:image/png;base64,{base64.b64encode(buf_m.getvalue()).decode()}"

    return b64_img, b64_msk, crop_region, (orig_w, orig_h), (crop_w, crop_h)


@app.post("/sh-api/demask")
async def api_demask(
    file: UploadFile = File(...),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    """
    AI demasking pipeline (Replicate):

    Step 1 — Skin-tone sampling
        Samples visible skin pixels from the forehead / neck region so the
        inpainting prompt is anchored to the subject's actual complexion.

    Step 2 — SD Inpainting (stability-ai/stable-diffusion-inpainting)
        An auto-generated mask covers only the face-covering region.
        SD inpainting fills ONLY that region; everything else is untouched.

    Step 3 — Composite back onto original
        The SD model outputs at 512 × 512.  We up-sample just the masked
        pixels and composite them back over the original full-resolution
        image so the result is never cropped or zoomed.

    CodeFormer is intentionally omitted — it turns faces into 3-D renders.

    Fallback — instruct-pix2pix with corrected guidance if inpainting fails.
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
        mask_bytes, face_boxes, used_heuristic = await asyncio.to_thread(
            _generate_face_coverage_mask, content
        )
        print(f"[Demask] Mask generated. used_heuristic={used_heuristic}")

        # ── 4. Sample visible skin tone, detect gender and facial hair ────────
        skin_tone_hint = await asyncio.to_thread(_sample_skin_tone, content, face_boxes)
        print(f"[Demask] Skin tone sampled: {skin_tone_hint}")

        if used_heuristic:
            # The heuristic face-box spans a huge region (10–72 % of height) that
            # does NOT correspond to real facial regions — the eyebrow-darkness
            # approach produces garbage results (often falsely "woman") when the
            # cap brim makes forehead + brow strip equally dark.  Fall back to
            # body-shape analysis instead.
            gender_hint = await asyncio.to_thread(_detect_gender_from_body, content)
            print(f"[Demask] Gender hint (body-based, heuristic mode): {gender_hint}")
        else:
            gender_hint = await asyncio.to_thread(
                _detect_gender_hint, content, face_boxes
            )
            print(f"[Demask] Gender hint (eyebrow-based): {gender_hint}")

        # ── 4b. Pre-fill gaiter region with skin colour ────────────────────────
        # This prevents SD from "replacing mask with mask" — the model sees
        # flesh-coloured pixels and generates facial features instead.
        prefilled_content = await asyncio.to_thread(
            _prefill_mask_with_skin, content, mask_bytes, face_boxes
        )

        # ── 5. Crop face region for focused, low-upscale inpainting ──────────
        # Sending just the face crop to SD (resized to 512×512) and pasting the
        # result back means we only upscale by ~1.3× instead of 2–3×, which
        # eliminates most of the plastic/smooth render look.
        print("[Demask] Preparing face crop for inpainting…")
        (
            crop_b64_img,
            crop_b64_mask,
            crop_region,
            orig_size,
            crop_size,
        ) = await asyncio.to_thread(
            _crop_for_inpainting, prefilled_content, mask_bytes, face_boxes
        )

        # ── 6. Resolve inpainting models ──────────────────────────────────────
        # Primary: lucataco/realistic-vision-v5-inpainting — photorealistic
        #          fine-tune of SD 1.5, produces natural skin texture and avoids
        #          the "plastic CGI face" characteristic of the base model.
        # Fallback: stability-ai/stable-diffusion-inpainting (SD 1.5 base)
        INPAINT_PRIMARY = "lucataco/realistic-vision-v5-inpainting"
        INPAINT_SECONDARY = "stability-ai/stable-diffusion-inpainting"

        v_inpaint_primary = None
        v_inpaint_secondary = None

        try:
            m_primary = await asyncio.to_thread(rep_client.models.get, INPAINT_PRIMARY)
            v_inpaint_primary = m_primary.latest_version.id
            print(f"[Demask] Primary model: {INPAINT_PRIMARY}@{v_inpaint_primary}")
        except Exception as e:
            print(f"[Demask] Could not fetch primary model ({e}); will use secondary.")

        try:
            m_secondary = await asyncio.to_thread(
                rep_client.models.get, INPAINT_SECONDARY
            )
            v_inpaint_secondary = m_secondary.latest_version.id
        except Exception:
            # Pinned SD 1.5 inpainting version as last resort
            v_inpaint_secondary = (
                "a9758cbfbd5f3c2094457d996681af52552901775aa2d6dd0b17fd15df959bef"
            )

        # ── 6b. Detect facial hair from visible jaw/cheek sides ───────────────
        facial_hair_result = await asyncio.to_thread(
            _detect_facial_hair, content, face_boxes
        )
        print(f"[Demask] Facial hair analysis: {facial_hair_result}")

        # Build prompt/negative dynamically based on detection result
        NEGATIVE_BASE = (
            "cartoon, 3d render, cgi, anime, illustration, painting, drawing, "
            "plastic skin, smooth skin, airbrushed, overly smooth, "
            "different gender, different ethnicity, new person, extra faces, "
            "mask, balaclava, face covering, surgical mask, sunglasses, "
            "distorted, blurry, deformed, bad anatomy, watermark, text, logo"
        )

        if facial_hair_result == "clean_shaven":
            # Confirmed no visible hair shadow — block it in generation too
            hair_positive = "clean shaven, no facial hair, smooth jawline,"
            hair_negative = (
                "beard, stubble, facial hair, mustache, goatee, five o'clock shadow,"
            )
            print("[Demask] Prompt: enforcing clean-shaven appearance.")
        elif facial_hair_result in ("has_facial_hair", "likely_facial_hair"):
            # Visible stubble/beard shadow — let the model keep it
            hair_positive = "with natural facial hair, stubble,"
            hair_negative = ""  # do NOT block beard in negative
            print("[Demask] Prompt: allowing/preserving facial hair.")
        else:
            # Unknown — stay neutral, do not force or block either way
            hair_positive = ""
            hair_negative = ""
            print("[Demask] Prompt: neutral on facial hair.")

        # NEGATIVE is finalised after gender detection below

        # ── 7. Inpainting on the face crop ────────────────────────────────────
        # guidance_scale 5.0: low enough to stay photographic, high enough to
        # actually follow "no mask". Lower = more natural skin, less "stylized".
        inpainted_url = ""

        gender_positive = f"{gender_hint}, " if gender_hint != "unknown" else ""
        gender_negative = (
            "woman, female, girl, "
            if gender_hint == "man"
            else "man, male, boy, "
            if gender_hint == "woman"
            else ""
        )

        # When we genuinely cannot determine gender (body analysis was
        # inconclusive AND the face was fully hidden), SD models are
        # statistically biased toward generating female faces.  Adding
        # soft anti-female terms here keeps the output gender-neutral
        # rather than defaulting female, without forcing "man" either.
        extra_gender_negative = ""
        if gender_hint == "unknown" and used_heuristic:
            extra_gender_negative = (
                "feminine features, female face, woman's face, girl's face, "
                "makeup, lipstick, mascara, eyeliner, "
            )
            print(
                "[Demask] Gender unknown in heuristic mode — "
                "adding anti-female-bias terms to negative prompt."
            )

        NEGATIVE = NEGATIVE_BASE + (
            (" " + hair_negative if hair_negative else "")
            + (" " + gender_negative if gender_negative else "")
            + (" " + extra_gender_negative if extra_gender_negative else "")
        )

        INPAINT_INPUT = {
            "image": crop_b64_img,
            "mask": crop_b64_mask,
            "prompt": (
                f"candid press photo, photojournalism, RAW photo, DSLR, "
                f"photo-realistic {gender_positive}human face, {skin_tone_hint}, "
                f"{hair_positive} "
                "natural skin texture, visible pores, film grain, realistic lighting, "
                "sharp focus, 8k, same ethnicity, no face covering, no mask, "
                "no surgical mask, open face, revealed face"
            ),
            "negative_prompt": NEGATIVE,
            "num_outputs": 1,
            "num_inference_steps": 60,
            # Lower guidance keeps skin texture natural and prevents the
            # over-stylised / plastic-skin look that 5.0+ causes.
            "guidance_scale": 4.0,
            # K_EULER_ANCESTRAL introduces stochastic noise at each step which
            # produces more organic, photographic skin compared to the fully
            # deterministic DPMSolverMultistep.
            "scheduler": "K_EULER_ANCESTRAL",
        }

        # ── 7a. Try primary (realistic-vision photorealistic fine-tune) ────────
        if v_inpaint_primary:
            print(f"[Demask] Running primary inpainting ({INPAINT_PRIMARY})…")
            try:
                out = await asyncio.to_thread(
                    rep_client.run,
                    f"{INPAINT_PRIMARY}:{v_inpaint_primary}",
                    input=INPAINT_INPUT,
                )
                inpainted_url = (
                    str(out[0]) if isinstance(out, list) and out else str(out or "")
                )
                if inpainted_url:
                    print(f"[Demask] Primary succeeded → {inpainted_url}")
            except Exception as e:
                print(f"[Demask] Primary inpainting failed ({e}); trying secondary.")

        # ── 7b. Fallback: SD 1.5 base inpainting ──────────────────────────────
        if not inpainted_url:
            print(f"[Demask] Running secondary inpainting ({INPAINT_SECONDARY})…")
            try:
                out = await asyncio.to_thread(
                    rep_client.run,
                    f"{INPAINT_SECONDARY}:{v_inpaint_secondary}",
                    input=INPAINT_INPUT,
                )
                inpainted_url = (
                    str(out[0]) if isinstance(out, list) and out else str(out or "")
                )
                if inpainted_url:
                    print(f"[Demask] Secondary succeeded → {inpainted_url}")
            except Exception as e:
                print(f"[Demask] Secondary inpainting failed: {e}")

        # ── 7c. Last-resort fallback: pix2pix on the full image ───────────────
        if not inpainted_url:
            print("[Demask] Falling back to instruct-pix2pix on full image…")
            mime = file.content_type or "image/jpeg"
            b64_full = f"data:{mime};base64,{base64.b64encode(content).decode()}"
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
                        "image": b64_full,
                        "prompt": (
                            f"reveal the face beneath the covering, {skin_tone_hint}, "
                            f"{hair_positive} "
                            "keep gender, ethnicity, hair, clothing and background "
                            "completely unchanged, realistic photo"
                        ),
                        "negative_prompt": NEGATIVE,
                        "num_inference_steps": 60,
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
                status_code=500, detail="Inpainting produced no output."
            )

        print(f"[Demask] Inpainting complete → {inpainted_url}")

        # ── 8. Composite crop result back onto the original ───────────────────
        # The SD result is 512×512 of the face crop.  We resize it back to the
        # crop's original pixel dimensions (e.g. 320×400) — a much smaller
        # upscale than going straight to full-image size — then paste it back
        # using the mask so only the covered region changes.
        print("[Demask] Compositing crop result onto original image…")
        try:
            from PIL import Image as PILImage

            async with httpx.AsyncClient() as hc:
                inp_resp = await hc.get(inpainted_url)
            inpainted_pil = PILImage.open(BytesIO(inp_resp.content)).convert("RGB")

            original_pil = PILImage.open(BytesIO(content)).convert("RGB")
            orig_w, orig_h = original_pil.size

            cl, ct, cr, cb = crop_region
            crop_w, crop_h = crop_size

            # Resize the 512×512 SD result back to the crop's native dimensions
            inpainted_crop = inpainted_pil.resize((crop_w, crop_h), PILImage.LANCZOS)

            # Get the matching crop of the full-res mask for compositing
            mask_pil_full = PILImage.open(BytesIO(mask_bytes)).convert("L")
            mask_crop_pil = mask_pil_full.crop((cl, ct, cr, cb))

            # composite(A, B, mask): A where mask=white, B where mask=black
            orig_crop = original_pil.crop((cl, ct, cr, cb))
            merged_crop = PILImage.composite(inpainted_crop, orig_crop, mask_crop_pil)

            # Paste the merged crop back onto a full-resolution copy of original
            result = original_pil.copy()
            result.paste(merged_crop, (cl, ct))

            out_buf = BytesIO()
            result.save(out_buf, format="PNG")
            out_buf.seek(0)
            return StreamingResponse(out_buf, media_type="image/png")

        except Exception as comp_err:
            print(f"[Demask] Composite failed ({comp_err}); returning raw inpaint.")
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
    request: Request,
    req: Optional[AuthVerifyReq] = Body(default=None),
    x_plugin_token: Optional[str] = Header(default=None, alias="X-Plugin-Token"),
):
    if req is None:
        req = AuthVerifyReq()
    client_ip = (request.client.host if request.client else None) or "unknown"

    if _login_limiter.is_locked(client_ip):
        _, _, lockout_sec = _LoginRateLimiter._limits()
        mins = lockout_sec // 60
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {mins} minute(s).")

    if not await _verify_hcaptcha(req.hcaptcha_token or ""):
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed.")

    try:
        require_admin(x_plugin_token)
    except HTTPException:
        remaining = _login_limiter.record_failure(client_ip)
        if remaining == 0:
            _, _, lockout_sec = _LoginRateLimiter._limits()
            mins = lockout_sec // 60
            raise HTTPException(status_code=429, detail=f"Too many failed attempts. Locked out for {mins} minute(s).")
        raise HTTPException(status_code=401, detail=f"Invalid token. {remaining} attempt(s) remaining.")

    _login_limiter.record_success(client_ip)
    return {"ok": True}


@app.get("/sh-api/public/theme")
async def api_public_theme():
    """Returns the current theme name without requiring authentication."""
    data = settings_store.load()
    theme = data.get("theme")
    if isinstance(theme, dict):
        return {"theme": theme.get("value") or "default"}
    return {"theme": theme or "default"}


@app.get("/sh-api/public/captcha-config")
async def api_captcha_config():
    """Returns hCaptcha site key for the login page. Public endpoint."""
    site_key = (os.getenv("HCAPTCHA_SITE_KEY") or "").strip()
    return {"enabled": bool(site_key), "site_key": site_key}


@app.get("/login")
async def login_page():
    return FileResponse(str(WEB_DIR / "login.html"))
