"""
HTTP wrapper around the DeepMosaics CLI.

Exposes:
  GET  /status   - service availability + model presence
  POST /process  - multipart: file, mode, mosaic_type, quality
                   returns the processed image/video bytes with X-Job-ID

Runs inside the deepmosaic container, which owns DeepMosaics/, torch and the
model weights. This keeps the heavy/vulnerable torch stack out of the main
Social-Hunt app container. The main app calls this over the internal docker
network via DEEPMOSAIC_URL.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

# Cross-platform defaults: Linux containers use /app/DeepMosaics; on Windows we
# resolve relative to this file so the same server.py runs in both worlds.
_DEFAULT_DM_DIR = (
    Path("/app/DeepMosaics")
    if os.name != "nt"
    else (Path(__file__).resolve().parents[2] / "DeepMosaics")
)
_TEMP_BASE = Path("/tmp") if os.name != "nt" else Path(os.getenv("TEMP", Path.cwd() / "tmp"))

DEEPMOSAIC_DIR = Path(os.getenv("DEEPMOSAIC_DIR", str(_DEFAULT_DM_DIR))).resolve()
DEEPMOSAIC_SCRIPT = DEEPMOSAIC_DIR / "deepmosaic.py"
RESULTS_DIR = Path(os.getenv("DEEPMOSAIC_RESULTS_DIR", str(_TEMP_BASE / "deepmosaic_results")))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = Path(os.getenv("DEEPMOSAIC_TEMP_DIR", str(_TEMP_BASE / "deepmosaic_temp")))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Social-Hunt DeepMosaic Worker")


def _model_path(*parts: str) -> Path:
    return DEEPMOSAIC_DIR / "pretrained_models" / Path(*parts)


def _models_present() -> dict:
    return {
        "clean_face_HD": _model_path("mosaic", "clean_face_HD.pth").exists(),
        "clean_youknow_v1": _model_path("mosaic", "clean_youknow_resnet_9blocks.pth").exists(),
        "add_face": _model_path("mosaic", "add_face.pth").exists(),
        "style_candy": _model_path("style", "edges2cat.pth").exists(),
        "style_monet": _model_path("style", "style_monet.pth").exists(),
    }


@app.get("/status")
async def status():
    return JSONResponse(
        {
            "available": DEEPMOSAIC_SCRIPT.exists(),
            "script": str(DEEPMOSAIC_SCRIPT),
            "models": _models_present(),
        }
    )


@app.post("/process")
async def process(
    file: UploadFile = File(...),
    mode: str = Form("clean"),
    mosaic_type: str = Form("squa_avg"),
    quality: str = Form("medium"),
):
    if not DEEPMOSAIC_SCRIPT.exists():
        return JSONResponse(
            status_code=500,
            content={"detail": f"deepmosaic.py not found at {DEEPMOSAIC_SCRIPT}"},
        )

    # Pre-check the model weights required for the requested mode so we can
    # return a clean, actionable error instead of a cryptic subprocess traceback.
    # The DeepMosaics CLI hard-codes a default model_path and only crashes inside
    # getparse() when the file is missing, so we surface the real cause here.
    if mode == "add":
        required = [_model_path("mosaic", "add_face.pth")]
    elif mode == "clean":
        required = [
            _model_path("mosaic", "clean_face_HD.pth"),
            _model_path("mosaic", "clean_youknow_resnet_9blocks.pth"),
        ]
    elif mode == "style":
        required = [_model_path("style", "edges2cat.pth"), _model_path("style", "style_monet.pth")]
    else:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unknown mode '{mode}'. Expected add | clean | style."},
        )

    missing = [str(p) for p in required if not p.exists()]
    if missing and not (mode == "clean" and any(p.exists() for p in required)):
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "DeepMosaic models are not downloaded. Run "
                    "`python download_deepmosaic_models.py --yes` (in the deepmosaic "
                    "venv) to fetch them. Missing: "
                    + ", ".join(missing)
                )
            },
        )

    job_id = str(uuid.uuid4())
    out_dir = RESULTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    in_path = TEMP_DIR / f"{job_id}_{safe_name}"
    in_path.write_bytes(await file.read())

    cmd = [
        sys.executable,
        "-u",
        "deepmosaic.py",
        "--media_path",
        str(in_path),
        "--mode",
        mode,
        "--result_dir",
        str(out_dir),
        "--temp_dir",
        str(out_dir / "temp"),
        "--no_preview",
    ]

    if mode == "add":
        add_model = _model_path("mosaic", "add_face.pth")
        if add_model.exists():
            cmd.extend(["--model_path", str(add_model)])
        cmd.extend(["--mosaic_mod", mosaic_type])
    elif mode == "clean":
        for model in (
            _model_path("mosaic", "clean_face_HD.pth"),
            _model_path("mosaic", "clean_youknow_resnet_9blocks.pth"),
        ):
            if model.exists():
                cmd.extend(["--model_path", str(model)])
                break
    elif mode == "style":
        style_model = _model_path("style", "edges2cat.pth")
        if style_model.exists():
            cmd.extend(["--model_path", str(style_model)])
        if quality == "high":
            cmd.extend(["--output_size", "1024"])
        elif quality == "low":
            cmd.extend(["--output_size", "256"])
        else:
            cmd.extend(["--output_size", "512"])

    print(f"[deepmosaic-worker] cmd: {' '.join(cmd)}", flush=True)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=str(DEEPMOSAIC_DIR),
    )

    # Video can be slow; allow 30 min.
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        try:
            in_path.unlink(missing_ok=True)
        except Exception:
            pass
        return JSONResponse(status_code=504, content={"detail": "DeepMosaic processing timeout"})

    stdout_str = stdout.decode("utf-8", errors="ignore")
    stderr_str = stderr.decode("utf-8", errors="ignore")

    if proc.returncode != 0:
        err = (stderr_str or stdout_str or "unknown error")[:500]
        try:
            in_path.unlink(missing_ok=True)
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={"detail": f"DeepMosaic failed (exit {proc.returncode}): {err}"},
        )

    # Find the newest output file in out_dir.
    outputs = [f for f in out_dir.rglob("*") if f.is_file()]
    if not outputs:
        return JSONResponse(status_code=500, content={"detail": "No output file generated"})

    outputs.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    out_file = outputs[0]

    media_type = "image/png"
    ext = out_file.suffix.lower()
    if ext == ".mp4":
        media_type = "video/mp4"
    elif ext == ".avi":
        media_type = "video/x-msvideo"
    elif ext == ".mov":
        media_type = "video/quicktime"
    elif ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".webp":
        media_type = "image/webp"
    elif ext == ".bmp":
        media_type = "image/bmp"

    data = out_file.read_bytes()

    # Clean up input + output to avoid filling disk.
    try:
        in_path.unlink(missing_ok=True)
        out_file.unlink(missing_ok=True)
    except Exception:
        pass

    return Response(
        content=data,
        media_type=media_type,
        headers={"X-Job-ID": job_id},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="info")