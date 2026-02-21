# Social-Hunt

Social-Hunt is an OSINT framework for cross-platform username discovery, breach exposure lookups, and avatar-based face matching. It ships with a web dashboard and a CLI, supports data-driven provider packs, and includes optional AI-powered face restoration/demasking.

## Features

- Username presence scanning across many platforms using YAML providers.
- Breach intelligence via Have I Been Pwned (HIBP), BreachVIP, and Snusbase — email, username, IP, and phone lookups across indexed breach databases.
- Face matching against profile avatars using face recognition and image hashing.
- Reverse image OSINT links (Google Lens, Bing, Yandex, etc.).
- Tor/Onion site support via SOCKS proxy (split-tunneling).
- Optional AI face restoration/demasking via Replicate, IOPaint, or DeepMosaic.
- Plugin system with hot-reload and optional web uploader.
- Demo mode that censors sensitive data for safe demonstrations.
- Dashboard theme applies immediately on selection.

## Tested Environments / VPS Compatibility

Known-good environments for self-hosting:

- Ubuntu 22.04 LTS (Jammy) on VPS providers (tested)
- Raspberry Pi 5 — Raspberry Pi OS (Bookworm, 64-bit) (tested — see [Raspberry Pi 5 Setup](#raspberry-pi-5-setup))

Notes:
- Other Debian/Ubuntu-based VPS images should work, but may require minor adjustments.
- If you deploy on a different OS/distro, please report your results in an issue or PR.

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

### Docker + bundled reverse proxy (nginx or apache)
Use a proxy profile to expose the app on port 80:
```bash
cd Social-Hunt/docker
# Nginx
docker compose --profile nginx up -d --build

# Apache
docker compose --profile apache up -d --build
```
Open `http://localhost/`.

To include IOPaint behind the same proxy:
```bash
docker compose --profile nginx --profile iopaint up -d --build
```

### Docker + SSL (nginx + IOPaint)
This enables HTTPS termination and routes `/` to Social-Hunt and `/iopaint` to IOPaint.
```bash
cd Social-Hunt/docker
python setup_ssl.py
docker compose --profile certbot run --rm --service-ports certbot
docker compose --profile ssl up -d
```
Open `https://your-domain`.

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

### Raspberry Pi 5 Setup

Social-Hunt runs on Raspberry Pi 5 (Raspberry Pi OS Bookworm, 64-bit). DeepMosaic is not recommended on Pi due to storage and compute constraints — all other features work.

The default system Python on Bookworm is 3.11+ which is fine, but `pip install -r requirements.txt` will fail due to Pillow and dlib compatibility issues with newer setuptools. The fix is to use **pyenv** to pin Python 3.11.9 and rebuild a clean venv.

#### 1. Install build dependencies

```bash
sudo apt update
sudo apt install -y build-essential curl git \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
  libsqlite3-dev libffi-dev libncursesw5-dev xz-utils \
  tk-dev libxml2-dev libxmlsec1-dev liblzma-dev
```

#### 2. Install pyenv

```bash
curl https://pyenv.run | bash
```

Add to `~/.bashrc`:

```bash
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
```

Reload the shell:

```bash
exec "$SHELL"
pyenv --version
```

#### 3. Install Python 3.11.9

```bash
pyenv install 3.11.9
cd ~/Social-Hunt
pyenv local 3.11.9
python --version   # must show 3.11.9
```

#### 4. Create venv and install dependencies

```bash
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 5. Run

```bash
python run.py
```

Open `http://localhost:8000` on the Pi, or `http://<pi-ip>:8000` from another device on the same network.

#### 6. Run as a systemd service (optional)

To have Social-Hunt start automatically on boot:

```bash
sudo nano /etc/systemd/system/socialhunt.service
```

Paste (replace `kittysec` with your username):

```ini
[Unit]
Description=Social Hunt OSINT Framework
After=network.target

[Service]
Type=simple
User=kittysec
WorkingDirectory=/home/kittysec/Social-Hunt
ExecStart=/home/kittysec/Social-Hunt/venv/bin/python run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable socialhunt
sudo systemctl start socialhunt
sudo systemctl status socialhunt
```

Useful commands:

```bash
sudo systemctl restart socialhunt   # after updates
sudo journalctl -u socialhunt -f    # live logs
```

#### Known Pi limitations

| Feature | Status |
| :-- | :-- |
| Username search | Works |
| Breach search | Works |
| Reverse image | Works |
| Google Dorks | Works |
| Secure Notes | Works |
| IOPaint inpainting | Works (CPU, slow) |
| Face matching | Works if dlib compiles |
| DeepMosaic | Not recommended (storage/compute) |

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
- `admin_token` — dashboard admin token; can be set via the Token page
- `hibp_api_key` — required for Have I Been Pwned breach lookups (get a key at [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key))
- `snusbase_api_key` — required for Snusbase breach record lookups (included with any paid membership at [snusbase.com](https://snusbase.com))
- `replicate_api_token` — required for Replicate-based demasking
- `public_url` — base URL for reverse-image links

Keys are added via **Settings → Add API** in the dashboard. Mark any key as **Secret** so the value is never returned to the browser after saving.

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
| `SOCIAL_HUNT_PROXY` | SOCKS proxy URL for `.onion`/darkweb access only (e.g., `socks5h://127.0.0.1:9050`) |
| `SOCIAL_HUNT_CLEARNET_PROXY` | HTTP/SOCKS proxy for clearnet providers that benefit from proxy routing (e.g., `http://user:pass@proxy.example.com:8080`) |
| `HCAPTCHA_SITE_KEY` | hCaptcha site key — enables CAPTCHA widget on the login page |
| `HCAPTCHA_SECRET` | hCaptcha secret key — required for server-side CAPTCHA verification |

## Login Security

### Rate limiting

The login endpoint (`/sh-api/auth/verify`) has built-in per-IP brute-force protection. Limits adjust automatically based on whether hCaptcha is configured:

| Mode | Max failures | Window | Lockout |
| :-- | :-- | :-- | :-- |
| No captcha (default) | 20 | 10 minutes | 60 seconds |
| hCaptcha active | 5 | 60 seconds | 5 minutes |

**If you lock yourself out**, the lockout is in-memory and clears on server restart:

```bash
# systemd
sudo systemctl restart socialhunt

# manual
# Ctrl+C the running process, then restart with python run.py
```

The lockout resets automatically after the lockout period even without a restart (60 s without captcha, 5 min with captcha).

### hCaptcha (optional)

Add a CAPTCHA challenge to the login form to block automated attacks. Uses [hcaptcha.com](https://hcaptcha.com) — free tier, no billing required.

**Setup:**

1. Sign up at [hcaptcha.com](https://hcaptcha.com) and create a new site.
2. Copy the **Site Key** and **Secret Key**.
3. Add to your environment file (`/etc/socialhunt.env` on Pi, or `.env`):

```bash
HCAPTCHA_SITE_KEY=your_site_key_here
HCAPTCHA_SECRET=your_secret_key_here
```

4. Restart the server. The CAPTCHA widget will appear on the login page automatically.

Without these env vars the login page works normally (no widget, relaxed rate limits).

## Breach Search / API Integrations

Breach Search runs lookups across four providers simultaneously. Each requires an API key added in **Settings → Add API** (mark as **Secret**).

| Provider | Key name | What it searches | Where to get a key |
| :-- | :-- | :-- | :-- |
| **Have I Been Pwned** | `hibp_api_key` | Email addresses against known breach databases | [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key) |
| **BreachVIP** | *(no key needed)* | Username / email / phone across breach dumps | [breach.vip](https://breach.vip) (free tier) |
| **Snusbase** | `snusbase_api_key` | Email, username, IP across indexed breach records | [snusbase.com](https://snusbase.com) (paid membership) |
| **LeakCheck** | `leakcheck_api_key` | Email, username, phone, and stealer log data | [leakcheck.io](https://leakcheck.io) — **Pro plan required** ($9.99/mo+); Basic/day plan does not include API access |

### Search type auto-detection

Snusbase automatically chooses the correct search field based on your input:

| Input format | Fields searched |
| :-- | :-- |
| Contains `@` and `.` | `email` |
| Digits only, 7–15 chars (phone) | `username`, `email` |
| Four dot-separated octets (IP) | `lastip` |
| Anything else | `email`, `username` |

### Provider statuses

| Status | Meaning |
| :-- | :-- |
| FOUND | At least one record returned |
| NOT FOUND | Query returned no results |
| SKIPPED / UNKNOWN | API key not set in Settings |
| BLOCKED | Rate-limited (429) or IP blocked (503) |
| ERROR | Network failure, timeout, or API error |

### Example: adding a Snusbase key

1. Go to **Settings** in the dashboard.
2. Click **Add API**.
3. Key: `snusbase_api_key` — Value: your activation code — check **Secret**.
4. Click **Save**. The key is picked up on the next scan without a restart.

## Tor / Darkweb Support

Social-Hunt supports scanning `.onion` sites by routing traffic through a Tor proxy. It uses split-tunneling — regular clearnet sites use your direct connection while `.onion` sites go through Tor.
For safety, avatar face matching skips `.onion` hosts.

### Prerequisites
1. Install Tor (e.g., `sudo apt install tor` or use Tor Browser).
2. Install SOCKS dependencies:
   ```bash
   pip install httpx[socks]
   ```

### Configuration
Set `SOCIAL_HUNT_PROXY` to your Tor SOCKS address. Use `socks5h://` to ensure DNS resolution happens over Tor (required for `.onion` hostnames).

**Linux/Mac:**
```bash
export SOCIAL_HUNT_PROXY="socks5h://127.0.0.1:9050"
python run.py
```

**Windows:**
```powershell
$env:SOCIAL_HUNT_PROXY="socks5h://127.0.0.1:9150"
python run.py
```
*(Standard Tor service uses port 9050; Tor Browser uses 9150.)*

> **Note:** `SOCIAL_HUNT_PROXY` is exclusively for Tor/`.onion` routing and is not used for clearnet providers. For clearnet proxy support see `SOCIAL_HUNT_CLEARNET_PROXY` below.

### Clearnet Proxy (optional)

Some clearnet providers (e.g. BreachVIP) can optionally route through a proxy — useful if your server IP is blocked. Set `SOCIAL_HUNT_CLEARNET_PROXY` to a residential or HTTP proxy:

```bash
export SOCIAL_HUNT_CLEARNET_PROXY="http://user:pass@proxy.example.com:8080"
python run.py
```

This is separate from Tor and has no effect on `.onion` routing. If unset, affected providers use your direct connection.

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

## AI Demasking (Replicate, IOPaint, or Self-Hosted)

Social-Hunt supports multiple demasking modes:
- Replicate API models (managed SaaS).
- IOPaint WebUI for interactive inpainting.
- DeepMosaic for automated mosaic removal (image/video).

### Replicate API
Set a Replicate API token in either:
- Settings: `replicate_api_token`
- Environment: `REPLICATE_API_TOKEN`

When configured, the server uses Replicate models to remove masks and restore facial detail.

### IOPaint (interactive)
Use the IOPaint page in the Demasking menu to:
- Start/stop the local IOPaint server
- Open the IOPaint WebUI
- Select model/device/port

You can also host IOPaint under `/iopaint` behind the same domain (see
`APACHE_SETUP.md` and `NGINX_SETUP.md`).

### DeepMosaic (automated)
DeepMosaic can remove mosaics from images or video. Use the DeepMosaic page to:
- Upload image/video
- Choose clean/add/style modes
- Download results or save to notes

### Self-hosted (custom)
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

- Locked out of login (too many failed attempts): the lockout is in-memory — restart the server (`sudo systemctl restart socialhunt` or `Ctrl+C` + `python run.py`) to clear it immediately. Without hCaptcha configured the lockout is only 60 seconds anyway.
- BreachVIP 503/blocked: breach.vip may block datacenter IPs. Results will show a BLOCKED status — no configuration change can bypass this; try from a residential IP or VPN.
- HIBP skipped: add `hibp_api_key` in Settings (get a key at [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key)).
- Snusbase skipped: add `snusbase_api_key` in Settings (included with any paid Snusbase membership at [snusbase.com](https://snusbase.com)). Mark it as **Secret**.
- API keys not taking effect: keys added in Settings are picked up immediately on the next scan — no server restart required.
- Missing Python providers: ensure `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1`.
- Demask not working: set `REPLICATE_API_TOKEN` or `SOCIAL_HUNT_FACE_AI_URL`.
- If the downloader fails for any reason, you may have to manually download the models from [Google Drive](https://drive.google.com/open?id=1LTERcN33McoiztYEwBxMuRjjgxh4DEPs) for DeepMosaics.

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
- `NGINX_SETUP.md` Nginx reverse proxy notes
- `docs/CANARY.md` canary warrant template
- `docs/PGP.md` PGP public key template
- `docs/NEWS_OSINT.md` OSINT news digest template
- `docs/CHANGELOG.md` version history and changes
- `docs/CONTRIBUTORS.md` project contributors
- `docs/peekyou.md` PeekYou provider usage notes
- `LICENSE` GPL-3.0

## Reverse Proxy Notes (IOPaint on same domain)

If you want IOPaint under the same domain (e.g., `/iopaint`), Social-Hunt's API
is moved to `/sh-api` to avoid conflicts with IOPaint's `/api` and `/socket.io`
routes. Make sure your reverse proxy routes `/sh-api` to the app and `/api` to
IOPaint as shown in `APACHE_SETUP.md`.
**SUPER IMPORTANT NOTE:** You must follow `APACHE_SETUP.md` or `NGINX_SETUP.md` for reverse proxy setup.

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
*Data breach lookup powered by HIBP, BreachVIP, and Snusbase — search by email, username, IP, or phone*

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
