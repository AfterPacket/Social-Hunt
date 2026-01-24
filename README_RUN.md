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

---

## 🔍 Troubleshooting

- **403 Forbidden on BreachVIP:** This is usually a Cloudflare block. Ensure your server IP is not on a known data center blacklist, or use the "Manual Search" button added to the UI.
- **HIBP Not Found:** Ensure your API key is active and has credits.
- **Missing Plugins:** Ensure `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1` is set in your environment if using Python-based providers.

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