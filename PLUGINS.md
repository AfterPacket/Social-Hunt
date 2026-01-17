# Social-Hunt Plugins

Social-Hunt supports "drop-in" plugins in two forms:

1) **YAML provider packs** (recommended)
2) **Python provider/addon plugins** (powerful, but executes code)

This document explains both, plus the optional web uploader.

## 1) YAML provider packs (safe / data-only)

Put one or more YAML files in:

```
plugins/providers/*.yaml
```

Each YAML file follows the same format as `providers.yaml`:

```yaml
my_site:
  url: "https://example.com/{username}"
  timeout: 10
  ua_profile: "desktop_chrome"
  success_patterns:
    - "{username}"
  error_patterns:
    - "not found"
```

These are loaded automatically at startup, and also on `/api/plugins/reload`.

## 2) Python plugins (executes code)

Python plugins are loaded from:

```
plugins/python/providers/*.py
plugins/python/addons/*.py
```

They are only loaded if you set:

```
SOCIAL_HUNT_ALLOW_PY_PLUGINS=1
```

### Provider plugin contract

A provider file must export either:

- `PROVIDERS = [ ... ]` list of provider instances, **or**
- `def get_providers() -> list:` returning provider instances

Provider instances must subclass `social_hunt.providers_base.BaseProvider`.

### Addon plugin contract

An addon file must export either:

- `ADDONS = [ ... ]` list of addon instances, **or**
- `def get_addons() -> list:` returning addon instances

Addon instances must subclass `social_hunt.addons_base.BaseAddon`.

⚠️ **Security note**: Python plugins run in the same process as the API.
Only enable this if you fully trust who can write to your plugins directory.

## Optional: Web uploader

The dashboard includes a **Plugins** panel that can upload a `.yaml` or a `.zip`.

To enable the web uploader:

```
SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1
SOCIAL_HUNT_PLUGIN_TOKEN=long_random_token
```

Then, in the dashboard, paste the token in "Admin Token".
Requests must include `X-Plugin-Token`.

### Zip upload contents

Accepted zip paths:

- `providers.yaml` or `providers.yml` (root)
- `providers/*.yaml` or `providers/*.yml`
- `python/providers/*.py` (only if `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1`)
- `python/addons/*.py` (only if `SOCIAL_HUNT_ALLOW_PY_PLUGINS=1`)

After upload, the server hot-reloads providers/addons so they appear immediately.
