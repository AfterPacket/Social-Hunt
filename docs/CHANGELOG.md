# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.2.3] - 2026-04-01

### Added

- **Voter Records** — New sidebar section and view providing a curated directory
  of 20+ official US state government voter registration lookup portals. States
  included: AZ, CO, FL, GA, IL, KS, KY, MD, MI, MN, NJ, NY, NC, OH, OK, OR,
  PA, SC, TX (county directory), UT, VA, WA, WI. Each card shows the state name,
  portal domain, and a direct "Open Portal" link. Includes a legal disclaimer
  and responsible-use notice.
- **README rewrite** — Full documentation overhaul. Added feature comparison
  table, per-feature guides (Google Dorks, Voter Records, Secure Notes, Breach
  Search, AI Demasking, Plugin System, Demo Mode, Tor support), full project
  directory tree, tested-environments table, updated Raspberry Pi setup
  instructions, expanded legal and ethics section.
- **CANARY.md update** — Warrant canary refreshed for Q2 2026 with PGP
  verification instructions, public key block, and next-update date (2026-07-01).
- `app.js` version bumped to `2.2.7` to ensure browser cache invalidation after
  all frontend changes in this release cycle.

### Changed

- **Voter Records** — Simplified from a search-form + API-call design to a clean
  static portal directory. Removed the search form (first name, last name, state
  dropdown, county), the `#vrResults` render pipeline, and the
  `initVoterRecordsView` JS function (~250 lines). Portal cards are now rendered
  directly from static HTML — no API call required on page load.
- **Voter Records portal links** — Corrected and updated several state URLs:
  - South Carolina: migrated from defunct `info.scvotes.sc.gov` to new portal at
    `vrems.scvotes.sc.gov`.
  - Georgia: corrected path from `/s/voter-registration-overview` (404) to `/s/`.
  - Texas: replaced defunct `teamrv-mvp.sos.state.tx.us` with the TX SOS county
    election office directory (TX voter registration is county-administered).
  - Added additional states: IL, KS, KY, MD, NJ, OK, OR, SC, UT, WA.
- **Voter Records deep-link templates** — Removed all query-parameter pre-fill
  attempts. All tested state voter portals (NC NCSBE, FL, VA, WI MyVote, OH,
  AZ, KS, MN) are JavaScript SPAs that ignore URL query parameters and render
  blank forms regardless of query string. The `_VOTER_DEEPLINK_TEMPLATES` dict
  is now empty; `prefilled` is always `False`.
- **Sidebar navigation** — "Voter Records" menu entry now appears after
  "Breach Search" in the sidebar.
- **Portal card text** — Updated to clearly say
  "Enter `<name>` in the search fields on the portal page" rather than making
  false pre-fill claims.
- **CSS cleanup** — Removed all search-form, result-card, party-badge,
  status-tag, source-tag, live-badge, and result-header styles from
  `voter-records.html` now that the search UI is gone. Retained only portal
  grid, portal card, disclaimer, and responsive breakpoint styles.

### Fixed

- **Voter Records 403 error** — The endpoint was registered under `/api/voter-records/search`,
  which conflicts with the nginx proxy rule that routes `/api/` to the IOPaint
  container. Moved to `/sh-api/voter-records/search` to match all other Social-Hunt
  API endpoints.
- **State dropdown contrast** — Voter Records state selector text was invisible
  (light text on white native dropdown background). Fixed by setting explicit
  `background: #1a2233` and `color: #e6edf3` on `<select>` and `<option>` elements.
- **NC voter parser column order** — The NC NCSBE voter lookup HTML table uses
  `County | Status | Full Name | City,State Zip` column order. The previous parser
  assumed `Name | Address | City | County | ...` and checked `cells[0]` (County)
  for the last name, causing every row to be skipped. Fixed column mapping and
  updated the City/State/Zip combined-cell parser.
- **Stale JS cache** — `app.js` version query string incremented from `2.2.2`
  through `2.2.7` across this release cycle to prevent browsers serving cached
  old JS after server restarts.
- **Python syntax error** — Stray `</thinking>` tag inserted into `api/main.py`
  during an edit session caused an `IndentationError` at startup. Removed.
- **Voter Records `prefilled` scoping** — Variable was conditionally assigned
  inside a branch and referenced outside it, causing a potential `NameError`.
  Initialised unconditionally before the branch.
- **`if state_portal:` indentation** — The TX-specific note block inside the
  `api_voter_records_search` endpoint had extra indentation (16 spaces instead of
  12) causing an `IndentationError`. Fixed.

### Removed

- `initVoterRecordsView()` function (~250 lines) from `app.js` — no longer needed
  now that the Voter Records view is a static HTML portal directory.
- `_try_nc_voter_lookup()`, `_try_fl_voter_lookup()`, `_try_va_voter_lookup()`,
  `_try_wi_voter_lookup()` scraping helpers from `api/main.py` — all targeted state
  portals are JavaScript SPAs or Cloudflare-protected and return 0 results or
  CAPTCHA pages to server-side HTTP requests. Live in-app results are not feasible
  without a headless browser runtime.
- Live-lookup labels (⚡ Live badges) from the Voter Records portal directory.
- The fake URL pre-fill query-parameter templates for NC, FL, VA, WI, AZ, KS, MN
  from `_VOTER_DEEPLINK_TEMPLATES`.

---

## [2.2.2] - 2026-02-14

### Added

- **Google Dorks view** — Built-in library of 100+ categorised Google search
  operator query templates. Categories: site/domain enumeration, file-type
  discovery, login/admin panel exposure, camera and IoT, email/username lookup,
  social media, code and API key exposure, subdomain enumeration, person/name
  search, company intelligence. One-click Search button opens query in Google.
  Bulk **Copy All** and **Download .txt** export.
- Google Dorks accessible from Search submenu in the sidebar.
- `initGoogleDorksView()` JS function — category filter dropdown, target input,
  dork generation, per-row Search buttons, export bar.

### Changed

- Sidebar **Search** menu item now expands a submenu containing
  **Google Dorks** as a sub-item.
- `viewTitles` and `viewInitializers` maps in `app.js` updated for `google-dorks`.

---

## [2.2.1] - 2026-02-01

### Added

- **Demo Mode toggle** in Settings — one-click enable/disable with live badge
  in the top bar. Censors emails, IPs, usernames, and other PII in all output.
- `SOCIAL_HUNT_DEMO_MODE` environment variable override.
- `saveDemoModeBtn` and `updateDemoMode()` in `app.js`.

### Changed

- Settings page layout refined — Public URL, Theme, Demo Mode, Update, and
  Restart controls separated into distinct sections.
- Dashboard stats refresh button now works without a full page reload.

### Fixed

- Breach Search results: LeakCheck `sources` array rendered as `[object Object]`
  in some edge cases. Now stringified correctly.
- Theme flash on hard refresh before JS loads — CSS custom properties now set
  via `<style>` in `<head>` before the app script runs.

---

## [2.2.0] - 2026-01-27

### Security

- **`protobuf` CVE-2024-5634** — Updated to `7.34.0rc1` to fix a denial-of-service
  vulnerability where a crafted message could bypass JSON recursion depth limits
  and crash the server.
- **`starlette` CVE-2024-37290** — Updated to `0.49.1`; `fastapi` updated to
  `0.128.0`. Fixes a DoS via malformed `Range` header in `FileResponse`.
- **`esptool` PYSEC-2023-234** — Pinned to `5.1.0`. Full upstream patch not yet
  available; monitoring for future releases.

### Changed

- `numpy` pinned to `2.2.6` to resolve incompatibility with the project's Python
  runtime.
- `xformers` upgraded to `0.0.34` (compatible with current `torch` version),
  resolving a strict dependency conflict.

---

## [2.1.0] - 2025-12-10

### Added

- **IOPaint integration** — Start, stop, and open an interactive IOPaint inpainting
  server directly from the dashboard. Model, device (CPU/CUDA/MPS), and port
  selection. Proxied under `/iopaint/` when using the nginx or Apache reverse proxy
  profiles.
- **DeepMosaic integration** — Automated mosaic removal from images and video via
  the DeepMosaic submodule. Upload, configure mode/quality, process, and download
  result or save to Secure Notes.
- `download_deepmosaic_models.py` helper script.
- Docker Compose `iopaint` service profile.
- `docker/nginx.conf` — routes `/` to Social-Hunt, `/iopaint/` to IOPaint,
  `/sh-api/` to Social-Hunt API, `/api/` to IOPaint internal API.
- `NGINX_SETUP.md` and `APACHE_SETUP.md` reverse-proxy guides.

### Changed

- Social-Hunt API prefix moved from `/api/` to `/sh-api/` to avoid path collision
  with IOPaint's `/api/` routes when hosted behind the same reverse proxy.
  All frontend fetch calls updated accordingly.
- Docker Compose `nginx` and `apache` profiles added alongside the default
  service-only compose file.

### Fixed

- IOPaint and Social-Hunt could not share the same domain due to `/api/` path
  conflict. Resolved by the `/sh-api/` migration.

---

## [2.0.0] - 2025-10-01

### Added

- **Secure Notes** — AES-256-GCM encrypted note vault in the browser.
  Notes stored in `localStorage`, never sent to the server unencrypted.
  PBKDF2 key derivation (310,000 iterations, SHA-256). Lock/unlock,
  create/edit/delete notes, export and import encrypted JSON vault.
- **Reverse Image OSINT** — Upload an image file or paste a URL; the app
  builds one-click search links for Google Lens, Bing Visual Search, Yandex
  Images, TinEye, Karma Decay, IQDB, and SauceNAO.
- **History tab** — Persistent log of all username searches, reverse image
  lookups, and demasking jobs. Re-open or re-run any past entry.
- **Plugin system** — Hot-reload YAML and Python provider packs. Optional
  web-based upload UI (`SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1`).
  ZIP bundle support for multi-file plugin packs.
- **hCaptcha support** — Optional CAPTCHA on the login page via
  `HCAPTCHA_SECRET` + `HCAPTCHA_SITEKEY` environment variables.
- **Dashboard** — Live system status indicators (server, token, providers),
  search statistics, rotating OSINT tips carousel, recent-searches quick-access.
- **Themes** — `default` (Social Hunt Dark), `tokyo` (Tokyo Night), `cobalt`.
  Applies instantly without page reload. Persisted in settings.
- **LeakCheck provider** — Breach Search now queries LeakCheck (Pro plan API key
  required).
- `SOCIAL_HUNT_CLEARNET_PROXY` environment variable for routing clearnet provider
  traffic through an HTTP/SOCKS proxy.
- Canary warrant template (`docs/CANARY.md`), PGP key placeholder (`docs/PGP.md`),
  and OSINT news digest template (`docs/NEWS_OSINT.md`).
- Docker Compose `build:` block for building from source.
- Raspberry Pi 5 setup guide in README.

### Changed

- Migrated from single `providers.yaml` to a split system: built-in
  `providers.yaml` + `plugins/providers/*.yaml` + `plugins/python/providers/*.py`.
- Login rate limiting reworked — progressive lockout (5 → 10 → 20 failures)
  with separate thresholds when hCaptcha is active.
- Settings page redesigned — all API keys, theme, public URL, demo mode,
  server update, and restart controls in one view.

### Fixed

- Face matching skipped for `.onion` hosts (privacy/safety).
- Job result pagination — large scans no longer block the event loop.

---

## [1.x] - Legacy

Earlier 1.x releases included the initial username scanning engine, HIBP +
BreachVIP + Snusbase breach search, basic face matching, YAML provider packs,
CLI interface, and the original single-page dashboard. See git history for
details.