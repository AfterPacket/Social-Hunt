# Social-Hunt Quick Start

## Installation

### Linux/Mac
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade setuptools pip
pip install -r requirements.txt
pip install python-multipart
```

### Windows (PowerShell)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade setuptools pip
pip install -r requirements.txt
pip install python-multipart
```

**If activation blocked:**
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Usage

### CLI Mode
```bash
# Basic scan
python -m social_hunt.cli username_here

# Specific platforms with JSON output
python -m social_hunt.cli username_here --platforms github reddit instagram --format json
```

### Web Interface (Recommended)
```bash
# Start server
uvicorn api.main:app --host 127.0.0.1 --port 8000

# Or bind to network interface
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

**Access:** http://127.0.0.1:8000/

---

## Configuration

### Admin Token (Required for Settings)
Protected endpoints require an admin token:

```bash
# Production: Set via environment variable
export SOCIAL_HUNT_PLUGIN_TOKEN="your-secure-token-here"

# Development: Enable bootstrap mode to set via web UI
export SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP=1
```

### Enable Plugin Uploads
```bash
export SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1
```

### HIBP (Have I Been Pwned) Integration
Configure in **Dashboard → Settings**:
- `hibp_api_key` - Your HIBP API key (required)
- `hibp_user_agent` - Identifying string for your app (required)
- `hibp_allow_non_email` - Set to `1` to check non-email usernames

---

## Notes

- **Bot Walls:** Some platforms (LinkedIn, TikTok) may return CAPTCHAs. Results show as `blocked` or `unknown`.
- **Metadata:** Results include `display_name`, `avatar_url`, `bio`, `followers` when available (extracted from Open Graph/JSON APIs).
- **IP Check:** Use `/api/whoami` to verify your public IP (useful when behind a proxy).
- **Privacy:** All searches run locally from your machine. No data sent to third parties.

---

## Troubleshooting

**Import Errors:** Make sure virtual environment is activated
```bash
source .venv/bin/activate  # Linux/Mac
.\.venv\Scripts\Activate.ps1  # Windows
```

**Port in Use:** Change port number
```bash
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

**Face Matcher Issues:** Ensure target images contain clear faces or use image hash matching for default avatars

---

For detailed documentation, see [README.md](README.md)