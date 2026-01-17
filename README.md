# 🕵️‍♂️ Social-Hunt 
### **Advanced Web + CLI OSINT Username Discovery**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-05998b)

**Social-Hunt** is a lightweight, high-performance OSINT engine designed to find usernames across hundreds of platforms. Unlike basic scrapers, it prioritizes **metadata depth** (followers, avatars, bios) and **transparency**—clearly distinguishing between a missing profile and a bot-wall.

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

---

## 📂 Project Structure

```txt
.
├── social_hunt/            # Core Engine
│   ├── providers/          # Python Plugins (High-fidelity data)
│   ├── engine.py           # Async scanning logic
│   ├── registry.py         # Plugin & YAML loader
│   └── rate_limit.py       # Pacing & Concurrency control
├── api/                    # FastAPI Server logic
├── web/                    # Frontend (HTML/JS/CSS)
├── providers.yaml          # Simple pattern-based definitions
└── requirements.txt        # Dependencies
🛠️ Installation
Windows
PowerShell
```

# Navigate to the directory
cd Social-Hunt

# Setup Virtual Environment
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Dependencies
python -m pip install -U pip
pip install -r requirements.txt
Linux / VPS
Bash

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
🖥️ Usage
1. Web Interface (Recommended)
Launch the API and UI locally:

Bash

python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
Access: Open http://127.0.0.1:8000/ in your browser.

2. Command Line (CLI)
Perform quick scans directly from your terminal:

Bash

# Basic scan
python -m social_hunt.cli username_here

# Targeted scan with JSON export
python -m social_hunt.cli username_here --platforms github reddit --format json
🔌 Extending the Tool
Option A: YAML (No-Code)
Add a new site to providers.yaml:

YAML

newsite:
  url: "[https://newsite.com/](https://newsite.com/){username}"
  timeout: 10
  ua_profile: "desktop_chrome"
  success_patterns: ["profile", "followers"]
  error_patterns: ["not found", "404"]
Option B: Python Plugin (Custom Logic)
For sites requiring API headers or complex parsing, create social_hunt/providers/newsite.py and subclass BaseProvider. Plugins can override YAML providers by using the same name.

🌐 API Documentation
Endpoint	Method	Description
/api/providers	GET	List all active YAML and Plugin providers.
/api/search	POST	Start a search job (returns job_id).
/api/jobs/{id}	GET	Poll for results and job state.
/api/whoami	GET	Check the IP address the engine is using.

Export to Sheets

🛡️ Security & Ethics
Ethical Use: Intended for authorized investigative work and OSINT research.

Best Effort: Social-Hunt respects robots.txt where possible, but platforms like LinkedIn or TikTok may block automated requests.

Deployment: If hosting publicly, use a reverse proxy (Apache/Nginx) with Basic Auth or IP allowlisting.

📄 License
This project is licensed under the GNU General Public License v3.0.


