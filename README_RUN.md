# 🏃‍♂️ Social-Hunt: Execution & Configuration Guide

This guide provides detailed instructions on how to set up, configure, and run **Social-Hunt** in various environments.

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed:
- **Python 3.9 or higher**
- **Git**
- **Docker & Docker Compose** (Optional, for containerized deployment)

---

## 🛠️ Manual Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-repo/Social-Hunt.git
cd Social-Hunt
```

### 2. Set Up a Virtual Environment (Recommended)
**Windows:**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
python -m pip install --upgrade pip setuptools
pip install -r requirements.txt
```

---

## ⚙️ Configuration Detail

Social-Hunt uses a combination of environment variables and a JSON settings file (`data/settings.json`).

### 1. Security & Tokens
To access the Dashboard, you need an **Admin Token**. You can set this in two ways:

#### A. Environment Variable (Highest Priority)
Set the token before launching the app:
```bash
export SOCIAL_HUNT_PLUGIN_TOKEN="your_secure_token_here"
```

#### B. Demo Mode (Optional)
Enable demo mode to showcase functionality while protecting personal data (censors results and limits output):
```bash
export SOCIAL_HUNT_DEMO_MODE="1"
```
You can also use `true/yes/on` as values.
If the env var is not set, demo mode can be toggled from the Settings page and is stored in `data/settings.json`.

#### C. Bootstrap Mode (Initial Setup)
If you don't want to use environment variables, enable bootstrap mode once:
1. Run with `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP=1`.
2. Open the browser to the **Token** page.
3. Set your token and save.
4. Restart the app without the bootstrap flag.

### 2. Settings Registry (`data/settings.json`)
| Key | Description |
| :--- | :--- |
| `hibp_api_key` | Required for Have I Been Pwned searches. |
| `public_url` | Your instance's URL (e.g., `https://osint.example.com`). Required for reverse image search to work with external engines. |
| `admin_token` | The fallback token if no environment variable is set. |
| `replicate_api_token` | Replicate API token for AI demasking. |

---

## 🚀 Running Social-Hunt

### Web Dashboard (FastAPI)
Launch the server using the provided runner:
```bash
python run.py
```
Alternatively, use Uvicorn directly:
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
**Access:** Open [http://localhost:8000](http://localhost:8000)

### Systemd (Auto-Restart for Restart Button)
The Settings page "Restart Server" button exits the process. To bring it back
up automatically, run under a supervisor such as systemd.

Manual Python (recommended):
```bash
sudo cp systemd/social-hunt.service.example /etc/systemd/system/social-hunt.service
sudo nano /etc/systemd/system/social-hunt.service
sudo systemctl daemon-reload
sudo systemctl enable social-hunt
sudo systemctl start social-hunt
```

Docker Compose (optional):
```bash
sudo cp systemd/social-hunt-docker.service.example /etc/systemd/system/social-hunt-docker.service
sudo nano /etc/systemd/system/social-hunt-docker.service
sudo systemctl daemon-reload
sudo systemctl enable social-hunt-docker
sudo systemctl start social-hunt-docker
```

### Command Line Interface (CLI)
Perform a quick scan without starting the web server:
```bash
python -m social_hunt.cli <username> --platforms github twitter reddit
```

---

## 🐳 Docker Deployment

Social-Hunt is fully containerized for easy deployment.

### 1. Build and Start
```bash
cd docker
docker-compose up -d --build
```

### 2. Docker Compose Configuration (`docker/docker-compose.yml`)
```yaml
services:
  social-hunt:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - SOCIAL_HUNT_PLUGIN_TOKEN=your_secure_token
      - SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1
    volumes:
      - ../data:/app/data
      - ../plugins:/app/plugins
```

### Docker SSL (Nginx + AI workers)
Use the SSL-aware Nginx proxy in `docker/docker-compose.yml`. This setup
terminates TLS and serves Social-Hunt at `/`. The AI workers (IOPaint,
DeepMosaic) run in sibling containers and are reached over the internal docker
network (`IOPAINT_URL`, `DEEPMOSAIC_URL`); IOPaint's web UI is opened directly on
port `8080` (separate origin) from the dashboard.

1) Generate the SSL config and env file:
```bash
cd docker
python setup_ssl.py
```

2) Issue a Let's Encrypt cert (uses port 80 temporarily):
```bash
docker compose --profile certbot run --rm --service-ports certbot
```

3) Start the stack with SSL:
```bash
docker compose --profile ssl up -d
```

Renewal (while nginx is running):
```bash
docker compose --profile certbot run --rm certbot renew --webroot -w /var/www/certbot
```

---

## 🔍 Troubleshooting

- **403 Forbidden on BreachVIP:** This is usually a Cloudflare block. Ensure your server IP is not on a known data center blacklist, or use the "Manual Search" button added to the UI.
- **HIBP Not Found:** Ensure your API key is active and has credits.
- **Missing Plugins:** Ensure `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1` is set in your environment if using Python-based providers.
- **Demask unavailable:** Set `REPLICATE_API_TOKEN` or point `SOCIAL_HUNT_FACE_AI_URL` to a compatible self-hosted worker.

---

## 🤖 AI Demasking (Replicate, IOPaint, or DeepMosaic)

Social-Hunt's demasking has three engines. The local ones (IOPaint,
DeepMosaic) run in **isolated environments** with their own torch + Pillow
9.5.0, separate from the main app (which stays on secure Pillow 12, no torch).
The app reaches them over loopback HTTP.

### Replicate API (cloud)
Set a Replicate API token in either:
- `replicate_api_token` in `data/settings.json`
- `REPLICATE_API_TOKEN` in your environment

### IOPaint (interactive inpainting)
IOPaint pins `Pillow==9.5.0` / `torch==2.1.2`, so it runs in its own venv
(Windows) or container (Docker `--profile ai`). Start the workers:

- **Docker**: `docker compose --profile ai up -d --build` (IOPaint on `:8080`)
- **Windows (no Docker)**: `powershell -ExecutionPolicy Bypass -File scripts\setup-ai.ps1` once, then `scripts\start-social-hunt.ps1`

The dashboard's **Open IOPaint WebUI** button opens `http://<host>:8080/`
(separate origin — IOPaint is not proxied under a subpath). See
`docker/docs/IOPAINT_GUIDE.md` for details.

### DeepMosaic (automated mosaic removal)
DeepMosaic runs in the same `--profile ai` (Docker) or `.venv-deepmosaic`
(Windows) environment. Models are not bundled — run
`python download_deepmosaic_models.py` once. The worker exposes a small HTTP
API on `:8081` (`/status`, `/process`); the app calls it via `DEEPMOSAIC_URL`.

### Self-hosted (custom endpoint)
Point Social-Hunt at your own face restoration service:
```bash
SOCIAL_HUNT_FACE_AI_URL=http://your-ai-host:port/restore
```
Expected request/response format:
```json
// POST with multipart/form-data: { "file": <image>, "strength": 0.5 }
// Response: { "image": "<base64-encoded-result>" }
```

See `FIXES.md` for why IOPaint/DeepMosaic are isolated from the main app.

---

## 🤝 Contributor Credits

We are grateful to the following individuals for their contributions to the development and stability of Social-Hunt:

- **Core Architecture:** **afterpacket**
- **Dependency & Build Optimization:** **airborne-commando** (Identified and tested critical `python-multipart` and `setuptools` requirements).
- **Breach Intelligence:** [Contributor Name]
- **Documentation & Research:** [Contributor Name]

---

## 📄 License
This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.
