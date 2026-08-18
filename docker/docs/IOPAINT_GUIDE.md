# AI Services Guide (IOPaint + DeepMosaic)

Social-Hunt's AI demasking features are powered by two optional workers that run
**separate** from the main app:

- **IOPaint** — interactive AI inpainting canvas. Web UI on port `8080`.
- **DeepMosaic** — automated mosaic removal over a small HTTP API. API on port `8081`.

Both workers depend on `torch` + `Pillow==9.5.0`, which are *intentionally* old
(iopaint 1.6.0 pins them and no newer release exists). To clear the known CVEs,
the main Social-Hunt app runs on **secure Pillow 12 with no torch** and talks to
the workers over loopback HTTP (`IOPAINT_URL` / `DEEPMOSAIC_URL`). This keeps the
vulnerable stack isolated and out of the app's dependency graph.

You can run the workers two ways: **Docker** (Linux servers) or **isolated
venvs** (Windows / no Docker). Both produce the same wiring.

---

## Option A — Docker (Linux / Docker Desktop)

Both workers are bundled under the `ai` compose profile. The main
`social-hunt` container is unchanged; it just gets `IOPAINT_URL` / `DEEPMOSAIC_URL`
pointed at the sibling containers.

### Start Social-Hunt + both AI workers

```bash
cd Social-Hunt/docker
docker compose --profile ai up -d --build
```

### Start with a reverse proxy too

```bash
# Nginx on :80
docker compose --profile nginx --profile ai up -d --build

# Apache on :80
docker compose --profile apache --profile ai up -d --build

# Nginx + SSL (Let's Encrypt)
python setup_ssl.py
docker compose --profile certbot run --rm --service-ports certbot
docker compose --profile ssl up -d --build
```

### Access

| Service | URL |
|---|---|
| Social-Hunt | `http://127.0.0.1:8000` |
| IOPaint WebUI | `http://127.0.0.1:8080` |
| DeepMosaic status | `http://127.0.0.1:8081/status` |

IOPaint's web UI is opened directly on port `8080` (a separate origin) from the
dashboard's **Open IOPaint WebUI** button. It is **not** proxied under `/iopaint/`
— IOPaint is a single-page app that assumes it is served at site root, so a
subpath proxy breaks its assets. See `FIXES.md` for the full reasoning.

### First-time startup

IOPaint's container installs `iopaint==1.6.0` (pulls torch + diffusers) on first
boot and downloads the `lama` model (~200MB). Expect 3-10 minutes depending on
bandwidth. Watch progress:

```bash
docker compose logs -f iopaint
# Wait for: INFO:     Uvicorn running on http://0.0.0.0:8080
```

DeepMosaic builds from `docker/deepmosaic/Dockerfile` and needs the DeepMosaics
submodule present on the host first:

```bash
# From the project root (one-time)
git submodule update --init DeepMosaics
```

If your copy was a ZIP download (no `.git`), clone it directly:

```bash
git clone https://github.com/HypoX64/DeepMosaics.git DeepMosaics
```

DeepMosaic models are **not** bundled. Check what's loaded:

```bash
curl http://127.0.0.1:8081/status
```

If models report `false`, run the downloader (in the container or on the host):

```bash
python download_deepmosaic_models.py
```

### Managing the workers

```bash
# Stop everything (app + AI workers)
docker compose --profile ai down

# Just the workers
docker compose stop iopaint deepmosaic

# Logs
docker compose logs -f iopaint
docker compose logs -f deepmosaic
```

---

## Option B — Non-Docker, isolated venvs (Windows / no Docker)

For Windows machines (or any host without Docker), two PowerShell scripts in
`scripts/` create isolated Python environments and launch all three services as
background processes. This is the **same** remote-mode wiring as the Docker
profile, just with local processes instead of containers.

### One-time setup

```powershell
# From the project root
powershell -ExecutionPolicy Bypass -File scripts\setup-ai.ps1
```

This creates:

- `.venv-iopaint` — `iopaint==1.6.0` (its own torch 2.1.2 + Pillow 9.5.0)
- `.venv-deepmosaic` — torch 2.1.2 + DeepMosaics + deps
- Clones `DeepMosaics/` if missing (handles ZIP-download case with no `.git`)
- Downloads DeepMosaic models (non-interactive)

Re-run with `-Force` to recreate the venvs.

### Start everything

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1
```

This launches three hidden background processes (logs in `data/logs/*.log`) and
sets `IOPAINT_URL` / `DEEPMOSAIC_URL` so the main app talks to the workers over
loopback. PIDs are tracked in `data/.ai-pids.json`.

### Stop everything

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1 -Stop
```

### Skip a worker

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1 -NoIOPaint
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1 -NoDeepMosaic
```

### Notes for the venv path

- The scripts resolve paths via `$PSScriptRoot`, so the space + parens in
  `Social-Hunt-main (1)` are handled. Do **not** run them from a renamed copy
  without re-testing.
- Use `127.0.0.1`, not `localhost` — uvicorn binds IPv4 `0.0.0.0` and Windows
  often resolves `localhost` to IPv6 `::1`, which is not served.
- IOPaint's torch cache is redirected to `data/iopaint-cache/` to avoid
  `~/.cache` permission issues under OneDrive folder redirection.

---

## How Social-Hunt reaches the workers

The main app reads two env vars at startup:

| Variable | Default (Docker) | Default (venv scripts) |
|---|---|---|
| `IOPAINT_URL` | `http://iopaint:8080` | `http://127.0.0.1:8080` |
| `DEEPMOSAIC_URL` | `http://deepmosaic:8081` | `http://127.0.0.1:8081` |

If a worker is unreachable, the corresponding demasking feature degrades
gracefully (the dashboard shows it as unavailable) — the rest of the app is
unaffected. If neither var is set, the app assumes the workers are not running.

This is why the workers can live in separate environments with conflicting
dependencies: the app never imports them, it only makes HTTP requests.

---

## Troubleshooting

### "Can't reach this page" at `http://127.0.0.1:8080`

- IOPaint is still installing on first boot. Check `docker compose logs iopaint`
  (Docker) or `data/logs/iopaint-stderr.log` (venv) and wait for the
  "Uvicorn running" line.
- On Windows, make sure you used `127.0.0.1` and not `localhost`.

### Port 8080 / 8081 already in use

Edit `docker/docker-compose.yml` (Docker) and change the host-side port:

```yaml
iopaint:
  ports:
    - "18080:8080"   # host:container
```

For the venv scripts, edit the `--port` argument in `scripts/start-social-hunt.ps1`
and the matching `IOPAINT_URL`.

### DeepMosaic `/process` returns 500

Models are missing. `curl http://127.0.0.1:8081/status` will show all models as
`false`. Run `python download_deepmosaic_models.py` (in `.venv-deepmosaic` for
the venv path, or inside the container for Docker).

### Permission denied writing to `~/.cache/torch` (Windows)

The venv scripts already redirect `TORCH_HOME` / `HF_HOME` / `XDG_CACHE_HOME`
to `data/iopaint-cache/`. If you launch IOPaint manually, set them yourself.

### `iopaint` / `deepmosaic` not detected by Social-Hunt

The app reads `IOPAINT_URL` / `DEEPMOSAIC_URL` at **startup**. Setting them after
the app is running has no effect — restart Social-Hunt.

---

## Quick reference

```bash
# Docker — start everything
docker compose --profile ai up -d --build

# Docker — stop everything
docker compose --profile ai down

# Windows venvs — one-time setup
powershell -ExecutionPolicy Bypass -File scripts\setup-ai.ps1

# Windows venvs — start
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1

# Windows venvs — stop
powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1 -Stop
```

| Service | Port | URL |
|---|---|---|
| Social-Hunt | 8000 | `http://127.0.0.1:8000` |
| IOPaint WebUI | 8080 | `http://127.0.0.1:8080` |
| DeepMosaic API | 8081 | `http://127.0.0.1:8081/status` |

---

## See also

- `FIXES.md` — why IOPaint/DeepMosaic are isolated, and the `/iopaint/` proxy bug.
- `NGINX_SETUP.md` / `APACHE_SETUP.md` — production reverse proxy config.
- `README_DOCKER.md` — general Docker setup.
- IOPaint: <https://github.com/Sanster/IOPaint>
- DeepMosaics: <https://github.com/HypoX64/DeepMosaics>