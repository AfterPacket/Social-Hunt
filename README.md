# 🕵️‍♂️ Social-Hunt 
### **Advanced Web + CLI OSINT Username Discovery**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-05998b)

**Social-Hunt** is a lightweight, high-performance OSINT engine designed to find usernames across hundreds of platforms. Unlike basic scrapers, it prioritizes **metadata depth** (followers, avatars, bios) and **transparency** clearly distinguishing between a missing profile and a bot-wall.

---

## 🚀 Key Features

* **Dual Interface:** Seamlessly switch between a modern **FastAPI Web UI** and a powerful **CLI**.
* **Rich Metadata:** Extracts more than just "Exists"—gets `display_name`, `avatar_url`, `bio`, and `follower_counts`.
* **Smart Statuses:** No more false negatives. Results are categorized as:
    * `FOUND` | `NOT_FOUND` | `UNKNOWN` | `BLOCKED` (Anti-bot detected) | `ERROR`
* **Hybrid Provider System:**
    * **YAML:** Quick-add sites via regex patterns.
    * **Python Plugins:** Custom logic for complex APIs (GitHub, Reddit) to bypass simple limitations.
* **Rate-Limit Aware:** Integrated per-host pacing and concurrency management.
* **Advanced Addons:**
    * **Face Matcher:** Dual-mode avatar comparison using:
        * Facial recognition for custom avatars with faces
        * Perceptual image hashing for default/generic avatars
    * **HIBP Integration:** Check breach exposure via Have I Been Pwned API
    * **Network Safety:** URL validation and content-type checking

---

## 📂 Project Structure

```txt
.
├── social_hunt/            # Core Engine
│   ├── providers/          # Python Plugins (High-fidelity data)
│   ├── addons/             # Extensible addon modules
│   ├── engine.py           # Async scanning logic
│   ├── registry.py         # Plugin & YAML loader
│   └── rate_limit.py       # Pacing & Concurrency control
├── api/                    # FastAPI Server logic
├── web/                    # Frontend (HTML/JS/CSS)
├── providers.yaml          # Simple pattern-based definitions
├── addons.yaml             # Addon configurations
└── requirements.txt        # Dependencies
```

---

## 🛠️ Installation

### Windows
```powershell
# Navigate to the directory
cd Social-Hunt

# Setup Virtual Environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Dependencies
python -m pip install -U pip
pip install -r requirements.txt
```

### Linux / VPS
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

---

## 🖥️ Usage

### 1. Web Interface (Recommended)
Launch the API and UI locally:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

**Access:** Open http://127.0.0.1:8000/ in your browser.

### 2. Command Line (CLI)
Perform quick scans directly from your terminal:

```bash
# Basic scan
python -m social_hunt.cli username_here

# Targeted scan with JSON export
python -m social_hunt.cli username_here --platforms github reddit --format json
```

---

## 🔐 Authentication & Configuration

### Login System
Social-Hunt protects the dashboard with a token-based login system:
1. **Initial Setup:** You must configure an Admin Token.
2. **Login:** Accessing the web interface redirects to a login page where you verify your token.
3. **Session:** The token is stored locally in your browser.

### Setting the Admin Token
You can set the Admin Token in one of two ways:
1. **Environment Variable (Recommended):** Set `SOCIAL_HUNT_PLUGIN_TOKEN` before starting the server.
2. **Bootstrap Mode:** 
   - Start the server with `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP=1`.
   - Go to the **Token** page in the UI to set your token.
   - Restart the server without the bootstrap flag.

### Environment Variables
| Variable | Description |
|----------|-------------|
| `SOCIAL_HUNT_PLUGIN_TOKEN` | Master admin token (overrides settings.json) |
| `SOCIAL_HUNT_SETTINGS_PATH` | Path to settings.json (default: data/settings.json) |
| `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP` | Allow setting token via UI (Set to `1` to enable) |
| `SOCIAL_HUNT_BOOTSTRAP_SECRET` | Optional secret for remote bootstrapping |

---

## 🎯 Face Matcher Addon

The Face Matcher addon enables identification of accounts by comparing avatar images using two complementary methods:

### Features
* **Face Recognition:** Detects and matches facial features in custom profile pictures
* **Image Hash Matching:** Compares images using perceptual hashing (perfect for default avatars)
* **Automatic Fallback:** Uses face matching when available, falls back to image hashing
* **Configurable Threshold:** Adjust sensitivity for image similarity matching

### How It Works
1. Load target images (with or without faces)
2. The addon extracts face encodings (if faces detected) and computes image hashes
3. For each found profile:
   - Downloads the avatar image
   - Attempts face matching first (if target has faces)
   - Falls back to image hash comparison
   - Reports match with method used (`face_recognition` or `image_hash`)

This dual approach allows you to identify:
- Accounts using the same person's photo
- Accounts using the same default/generic avatar
- Accounts that reused the same uploaded image (logo, artwork, etc.)

---

## 🔌 Extending the Tool

### Option A: YAML (No-Code)
Add a new site to `providers.yaml`:

```yaml
newsite:
  url: "https://newsite.com/{username}"
  timeout: 10
  ua_profile: "desktop_chrome"
  success_patterns: ["profile", "followers"]
  error_patterns: ["not found", "404"]
```

### Option B: Python Plugin (Custom Logic)
For sites requiring API headers or complex parsing, create `social_hunt/providers/newsite.py` and subclass `BaseProvider`. Plugins can override YAML providers by using the same name.

Example:
```python
from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus

class NewSiteProvider(BaseProvider):
    name = "newsite"
    
    async def check(self, username, client, headers):
        # Your custom logic here
        pass
```

---

## 🌐 API Documentation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/providers` | GET | List all active YAML and Plugin providers |
| `/api/search` | POST | Start a search job (returns `job_id`) |
| `/api/jobs/{id}` | GET | Poll for results and job state |
| `/api/whoami` | GET | Check the IP address the engine is using |

---

## 🛡️ Security & Ethics

* **Ethical Use:** Intended for authorized investigative work and OSINT research.
* **Best Effort:** Social-Hunt respects `robots.txt` where possible, but platforms like LinkedIn or TikTok may block automated requests.
* **Deployment:** If hosting publicly, use a reverse proxy (Apache/Nginx) with Basic Auth or IP allowlisting.
* **Privacy:** No data is stored or transmitted to third parties. All searches are performed directly from your machine.

---

## 📝 Recent Improvements

* **Secure Login System:** Token-based authentication for web dashboard
* **Enhanced Metadata Extraction:** Improved parsing with suppressed false-positive warnings
* **Dual Avatar Matching:** Face recognition + image hashing for comprehensive profile matching
* **Better Error Handling:** More descriptive error messages for debugging
* **Cleaner Logs:** Reduced console spam from HTML parsing warnings

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0**.

See [LICENSE](LICENSE) for details.

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Add new providers via YAML or Python plugins
- Report bugs or suggest features via GitHub Issues
- Submit pull requests with improvements

---

## 📖 Additional Documentation

See [README_RUN.md](README_RUN.md) for quick start commands and configuration options.
