# Social-Hunt (Web + CLI)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Windows Install (PowerShell)

```powershell
cd C:\path\to\social-hunt-webapp
py -m venv .venv
\.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## CLI

```bash
python -m social_hunt.cli afterpacket --format json
python -m social_hunt.cli afterpacket --platforms github reddit instagram
```

## Web (FastAPI)

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

### Windows run

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open:
- http://127.0.0.1:8000/

## Your IP (as seen by the API)

The web UI shows your IP using `/api/whoami`. This is helpful when running behind Apache/Nginx
to confirm `X-Forwarded-For` is being passed correctly.

## Notes
- Some platforms may return bot-walls (CAPTCHA / login). Those show as `blocked` or `unknown`.
- This is an OSINT presence checker for **public** profile pages.

## Metadata
Each result includes a best-effort `profile` object. For many sites this is pulled
from Open Graph / Twitter Card metadata (`og:title`, `og:image`, etc.).

Some providers use JSON endpoints/APIs when available:
- GitHub: public user endpoint can return avatar URL, followers/following, and `created_at`.
- Reddit: `/user/{username}/about.json` commonly exposes `created_utc` and karma fields.

Creation dates are not public on many platforms; treat them as optional.

## Addons (post-scan enrichment)

Social-Hunt can run optional **addons** after the provider scan to enrich results.
Enabled addons are configured in `addons.yaml`.

Included addons:
- `bio_links`: extract URLs/domains/@handles from public bios/descriptions.
- `avatar_fingerprint`: download avatar URLs (with SSRF/size/timeouts) and compute `avatar_sha256` + `avatar_dhash`.
- `avatar_clusters`: cluster providers when avatars match (exact sha256, or near-match dHash).

API helpers:
- `GET /api/addons` lists available + enabled addons.
- `POST /api/reverse_image_links` returns one-click links for common reverse-image search engines (Google Images, Google Lens, Bing, TinEye, Yandex).
- `POST /api/reverse_image` compares a query image URL against the avatar fingerprints in an existing job (scoped to that job).
