# Social-Hunt

Social-Hunt is an OSINT framework for cross-platform username discovery, breach exposure lookups, and avatar-based face matching. It ships with a web dashboard and a CLI, supports data-driven provider packs, and includes optional AI-powered face restoration/demasking.

## Features

- Username presence scanning across many platforms using YAML providers.
- Breach intelligence via Have I Been Pwned (HIBP) and BreachVIP.
- Face matching against profile avatars using face recognition and image hashing.
- Reverse image OSINT links (Google Lens, Bing, Yandex, etc.).
- Tor/Onion site support via SOCKS proxy (split-tunneling).
- Optional AI face restoration/demasking via Replicate or a self-hosted worker.
- Plugin system with hot-reload and optional web uploader.
- Demo mode that censors sensitive data for safe demonstrations.
- Dashboard theme applies immediately on selection.

## Architecture

- Backend: FastAPI + httpx async scanning engine.
- Frontend: Static HTML/CSS/JS dashboard (no heavy framework).
- Core engine: async concurrency with per-provider rules and status heuristics.

## Quick Start

### Docker (recommended)
```bash
git clone https://github.com/AfterPacket/Social-Hunt.git
cd Social-Hunt/docker
docker-compose up -d --build
```
Open `http://localhost:8000`.

### Manual install
```bash
git clone https://github.com/AfterPacket/Social-Hunt.git
cd Social-Hunt
python -m pip install -r requirements.txt
# For Tor/SOCKS support, ensure httpx-socks is installed:
python -m pip install httpx[socks]
python run.py
```
Open `http://localhost:8000`.

For a full setup guide (virtualenv, tokens, Docker details), see `README_RUN.md`.

## CLI Usage

```bash
python -m social_hunt.cli <username> --platforms github twitter reddit
```

Useful options:
- `--format csv|json` (default: csv)
- `--max-concurrency 6`
- `--face-match /path/to/image1.jpg /path/to/image2.png`
- `--verbose` (writes `social_hunt.log`)

## Configuration

### Settings file

Settings are stored in `data/settings.json` (or `SOCIAL_HUNT_SETTINGS_PATH`).

Common keys:
- `admin_token` (dashboard admin token; can be set via the Token page)
- `hibp_api_key` (required for HIBP)
- `replicate_api_token` (required for Replicate-based demasking)
- `public_url` (base URL for reverse-image links)

Settings resolution order is:
1) `data/settings.json` (or `SOCIAL_HUNT_SETTINGS_PATH`)
2) environment variables: `KEY`, `KEY` uppercased, `SOCIAL_HUNT_<KEY uppercased>`

### Environment variables

| Variable | Purpose |
| :-- | :-- |
| `SOCIAL_HUNT_HOST` | Bind address (default: `0.0.0.0`) |
| `SOCIAL_HUNT_PORT` | Server port (default: `8000`) |
| `SOCIAL_HUNT_RELOAD` | Enable auto-reload (`1` for dev) |
| `SOCIAL_HUNT_SETTINGS_PATH` | Override `data/settings.json` |
| `SOCIAL_HUNT_PROVIDERS_YAML` | Override `providers.yaml` |
| `SOCIAL_HUNT_JOBS_DIR` | Override jobs output directory |
| `SOCIAL_HUNT_PUBLIC_URL` | Base URL for reverse image engines |
| `SOCIAL_HUNT_PLUGIN_TOKEN` | Admin token for protected actions |
| `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP` | Allow setting admin token in UI |
| `SOCIAL_HUNT_BOOTSTRAP_SECRET` | Alternative bootstrap guard via `X-Bootstrap-Secret` |
| `SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD` | Allow plugin uploads in dashboard |
| `SOCIAL_HUNT_ALLOW_PY_PLUGINS` | Allow Python plugins (executes code) |
| `SOCIAL_HUNT_PLUGIN_DIR` | Upload target for web plugins (default: `plugins/providers`) |
| `SOCIAL_HUNT_PLUGINS_DIR` | Base plugins directory (default: `plugins`) |
| `SOCIAL_HUNT_DEMO_MODE` | Censor sensitive fields in results |
| `SOCIAL_HUNT_FACE_AI_URL` | External face restoration endpoint |
| `REPLICATE_API_TOKEN` | Replicate API token for demasking |
| `SOCIAL_HUNT_PROXY` | SOCKS Proxy URL for .onion/darkweb access (e.g., `socks5h://127.0.0.1:9050`) |

## Tor / Darkweb Support

Social-Hunt supports scanning `.onion` sites by routing traffic through a Tor proxy. It uses split-tunneling, so regular sites (like Twitter) use your direct connection while `.onion` sites go through the proxy.
For safety, avatar face matching skips `.onion` hosts.

### Prerequisites
1. Install Tor (e.g., `sudo apt install tor` or use Tor Browser).
2. Install SOCKS dependencies:
   ```bash
   pip install httpx[socks]
   ```

### Configuration
Set the `SOCIAL_HUNT_PROXY` environment variable before starting the app. Use `socks5h://` to ensure DNS resolution happens over Tor.

**Linux/Mac:**
```bash
export SOCIAL_HUNT_PROXY="socks5://127.0.0.1:9050"
python run.py
```

**Windows:**
```powershell
$env:SOCIAL_HUNT_PROXY="socks5h://127.0.0.1:9150"
python run.py
```
*(Note: Standard Tor service uses port 9050; Tor Browser usually uses 9150).*

## Plugins

Social-Hunt supports YAML provider packs and optional Python plugins:

- YAML providers: `plugins/providers/*.yaml`
- Python providers/addons: `plugins/python/providers/*.py`, `plugins/python/addons/*.py`

To enable Python plugins, set `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1`.

The dashboard can upload `.yaml` or `.zip` bundles when:

```
SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1
SOCIAL_HUNT_PLUGIN_TOKEN=long_random_token
```

See `PLUGINS.md` for full details and plugin contracts.

## Reverse Image OSINT

Reverse-image links require a public base URL for your instance:

- Set `public_url` in settings or `SOCIAL_HUNT_PUBLIC_URL` in the environment.

## AI Demasking (Replicate or Self-Hosted)

Social-Hunt can run the demasking pipeline with Replicate or a self-hosted worker.

### Replicate API
Set a Replicate API token in either:
- Settings: `replicate_api_token`
- Environment: `REPLICATE_API_TOKEN`

When configured, the server uses Replicate models to remove masks and restore facial detail.

### Self-hosted (DeepMosaics or custom)
Set `SOCIAL_HUNT_FACE_AI_URL` to an HTTP endpoint that accepts JSON:
```json
{
  "image": "<base64 image bytes>",
  "fidelity": 0.7,
  "task": "face_restoration"
}
```
and returns:
```json
{ "image": "<base64 restored image bytes>" }
```

The repo includes a `DeepMosaics/` submodule you can use to build a local restoration service,
but it does not match the `/restore` JSON contract out of the box. Add a small adapter or
proxy to translate the request/response format, then point `SOCIAL_HUNT_FACE_AI_URL` at it.

## Troubleshooting

- BreachVIP 403: Cloudflare may block datacenter IPs. Try manual search or change IP.
- HIBP skipped: missing or invalid `hibp_api_key`.
- Missing Python providers: ensure `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1`.
- Demask not working: set `REPLICATE_API_TOKEN` or `SOCIAL_HUNT_FACE_AI_URL`.

## Project Structure

- `api/` FastAPI app and settings store
- `social_hunt/` core engine, registry, providers, addons, CLI
- `web/` static dashboard UI
- `plugins/` YAML providers and optional Python plugins
- `data/` settings and scan jobs
- `docker/` container build/deploy files

## Documentation

- `README_RUN.md` execution and configuration guide
- `PLUGINS.md` plugin formats and uploader
- `APACHE_SETUP.md` Apache reverse proxy notes
- `LICENSE` GPL-3.0

## Reverse Proxy Notes (IOPaint on same domain)

If you want IOPaint under the same domain (e.g., `/iopaint`), Social-Hunt’s API
is moved to `/sh-api` to avoid conflicts with IOPaint’s `/api` and `/socket.io`
routes. Make sure your reverse proxy routes `/sh-api` to the app and `/api` to
IOPaint as shown in `APACHE_SETUP.md`.

## Screenshots / UI Tour

### Login
![Login Screen](assets/screenshots/login.png)
*Self-hosted OSINT aggregator with admin token authentication*

### Dashboard
![Dashboard Overview](assets/screenshots/dashboard.png)
*Main dashboard showing welcome screen and recent job history*

### Username Search
![Search Results](assets/screenshots/search-results.png)
*Comprehensive username search across 500+ platforms with real-time status indicators*

### Breach Search
![Breach Search](assets/screenshots/breach-search.png)
*Data breach lookup powered by BreachVIP*

### Reverse Image Search
![Reverse Image](assets/screenshots/reverse-image.png)
*Reverse image search with multiple engine options (Google Lens, Bing, Yandex)*

### AI Face Restoration
![Demasking](assets/screenshots/demasking.png)
*Forensic AI demasking using Replicate or self-hosted models*

### History
![History](assets/screenshots/history.png)
*Search History*

### Secure Notes
![Secure Notes - List](assets/screenshots/secure-notes.png)
*Encrypted notes with AES-256-GCM encryption*

![Secure Notes - Master Password](assets/screenshots/secure-notes-password.png)
*Master password protection for secure notes*

### Plugin System
![Plugins](assets/screenshots/plugins.png)
*YAML provider packs and plugin upload interface*

### Settings & Configuration
![Settings](assets/screenshots/settings.png)
*Server configuration, theme selection, and API integrations*

### Token Management
![Token Management](assets/screenshots/token.png)
*Admin token and browser token management*





## Contributors

Thanks to everyone who has helped build and maintain Social-Hunt.
Add contributors here or link to a CONTRIBUTORS file if you prefer.

## Legal and Ethics

Social-Hunt is for lawful, authorized investigations only. You are responsible for complying with platform terms and local laws.
