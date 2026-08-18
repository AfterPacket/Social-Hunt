# Notable fixes

Bugs whose cause was not where the symptom pointed. Kept because the reasoning
is worth more than the diff — several of these were expensive to find, and the
next one will look just as innocent.

---

## IOPaint and DeepMosaic could not coexist with a secure Pillow

**Symptom.** `pip install -r requirements.txt` fails:

```
ERROR: Cannot install -r requirements.txt (line 34) and pillow<13.0.0 and >=12.0.0
because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested pillow<13.0.0 and >=12.0.0
    iopaint 1.6.0 depends on Pillow==9.5.0
```

Twenty-five Dependabot alerts open, all on Pillow 9.5.0 and torch 2.1.2 — the
exact versions iopaint 1.6.0 pins.

**Cause.** `iopaint==1.6.0` hard-pins `Pillow==9.5.0` and `torch==2.1.2` in its
own metadata. The main app needs `pillow>=12.0.0` to clear the CVEs. A single
`pip install` cannot satisfy both — they are mutually exclusive version ranges
in the same environment. The same conflict applies to `torch==2.1.2` (multiple
critical CVEs) and to DeepMosaics, which was written against the old torch.

**Why it hid.** The error message names Pillow and reads like a version-range
disagreement you can loosen. Loosening `pillow>=12.0.0` reopens every CVE;
loosening `iopaint`'s pin is impossible because the pin is in iopaint's
metadata, not yours. The two constraints have no intersection, and the
diagnostic does not say "these cannot coexist" — it says "try loosening", which
sends you in a circle.

**Fix.** IOPaint and DeepMosaic run in **isolated environments** — separate
venvs on Windows (`scripts/setup-ai.ps1`), separate containers on Linux
(`docker compose --profile ai`). The main app stays on secure Pillow 12 with no
torch. It talks to the AI workers over loopback HTTP (`IOPAINT_URL`,
`DEEPMOSAIC_URL`) rather than importing them. This is the same wiring the
docker-compose `ai` profile uses; the PowerShell scripts are the venv
equivalent.

**Avoid it.** When a dependency pins a vulnerable version of a library you also
use, the pin is in *their* metadata — you cannot loosen it from yours. The only
resolution is isolation: separate environments that do not share the constraint.
A single `requirements.txt` is the wrong shape for a project that mixes secure
and intentionally-legacy stacks.

---

## The space in the project path silently truncated every script path

**Symptom.** All three background services start, print their PIDs, and die
before answering a single request. The log says:

```
python.exe: can't open file 'C:\Users\jorda\OneDrive\Documents\Social-Hunt-main':
[Errno 2] No such file or directory
```

Notice the path ends at `Social-Hunt-main` — the ` (1)\Social-Hunt-main\...`
suffix is gone.

**Cause.** The project directory is `Social-Hunt-main (1)` — a space and
parentheses, from a ZIP download that was extracted next to a prior copy. The
start script launched Python with:

```powershell
Start-Process -FilePath $DmPy -ArgumentList @($ServerPy) ...
```

`Start-Process -ArgumentList` splits each element on spaces when building the
command line. A path containing a space becomes two arguments. Python receives
`C:\Users\jorda\OneDrive\Documents\Social-Hunt-main` as the script name and
`(1)\Social-Hunt-main\docker\deepmosaic\server.py` as a second argument it
ignores. The file at the truncated path does not exist, so Python exits
immediately.

**Why it hid.** `Start-Process` reported success and returned a PID — the
process *did* start, it just exited in under a second. The PID was saved, the
summary printed "pid 27644 -> http://127.0.0.1:8081/status", and everything
looked correct from the launcher's perspective. Only `curl` against the port
returned connection refused, and only the redirected stderr log showed the
truncated path. When the same Python command was run directly in the terminal
the shell quoted the path correctly, so manual testing passed but the script
failed.

**Fix.** Quote the argument explicitly:

```powershell
Start-Process -FilePath $DmPy -ArgumentList "`"$ServerPy`"" ...
```

The backtick-quote produces a literal `"` inside the argument string, so the
Windows command line parser sees `"C:\...\Social-Hunt-main (1)\...\server.py"`
as one token. IOPaint's arguments contain no spaces, so a plain string works for
it.

**Avoid it.** `Start-Process -ArgumentList @($var)` is not safe for paths
containing spaces. PowerShell's argument passing to native commands has been a
known hazard since 1.0 — the array form splits on spaces, the string form does
not. Any path with a space, parenthesis, or ampersand will be truncated. Test
launchers from a directory whose name contains a space, not from `C:\Git\`.

---

## The emoji in the startup banner crashed the server on Windows

**Symptom.** `python run.py` works when typed at the PowerShell prompt, but the
same command launched via `Start-Process` crashes before the server starts:

```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 6-10:
character maps to <undefined>
```

**Cause.** `run.py` prints:

```python
print("      🕵️‍♂️ Social-Hunt OSINT Framework")
```

When run from an existing PowerShell window, the console's code page is
typically UTF-8 (or the `PYTHONIOENCODING` env var is set in the user profile).
When `Start-Process` opens a *new* console window, that window inherits the
system default code page — `cp1252` on a US-English Windows install. `cp1252`
has no mapping for the detective emoji, so `print()` raises
`UnicodeEncodeError` and the process exits before uvicorn starts.

**Why it hid.** The crash happened in a background window that closed
immediately. The error went to stderr, which `Start-Process` without
`-RedirectStandardError` discards. The PID was saved, the launcher reported
success, and the only symptom was `HTTP 000` on port 8000 — which looks
identical to "the server is still starting". Running the same command
interactively worked perfectly, because the interactive shell had a different
code page.

**Fix.** Two layers. The start script sets `$env:PYTHONIOENCODING = 'utf-8'`
and `$env:PYTHONUTF8 = '1'` before launching any Python process, so the new
console uses UTF-8 regardless of the system code page. And `run.py` wraps the
emoji print in a `try/except UnicodeEncodeError` that falls back to the plain
ASCII string, so the server starts even if the env var is missing.

**Avoid it.** A Python process that prints non-ASCII to stdout will crash on any
Windows console that is not UTF-8. The default `cp1252` cannot handle emoji,
CJK, or most accented characters. `PYTHONUTF8=1` is the process-wide fix;
`PYTHONIOENCODING=utf-8` is the stdio-only fix. Neither is on by default. Any
launcher that opens a new console must set one of them.

---

## IOPaint died with permission denied writing to the torch cache

**Symptom.** IOPaint starts, prints its banner, and crashes:

```
PermissionError: [WinError 5] Access is denied: 'C:\\Users\\jorda\\.cache\\torch'
```

**Cause.** `torch.hub.get_dir()` defaults to `~/.cache/torch`. On this machine
`~/.cache` either does not exist or is not writable — the `OneDrive`
redirection of the user profile can make `~/.cache` a synced folder with
restricted permissions, and creating subdirectories inside it fails. IOPaint's
`scan_models()` calls `get_cache_path_by_url()` which calls `os.makedirs()` on
that path, and the `WinError 5` propagates up as an unhandled exception during
startup.

**Why it hid.** The error is not about IOPaint's code — it is about a
filesystem permission on a path torch chose. The traceback points at
`helper.py:39` inside IOPaint, which reads like an IOPaint bug, but the actual
constraint is "the user's home directory cache is not writable". On Linux the
same path is always writable; on Windows under OneDrive it may not be.

**Fix.** The start script redirects torch's cache into the project tree:

```powershell
$IopaintCache = Join-Path $Root 'data\iopaint-cache'
$env:TORCH_HOME     = Join-Path $IopaintCache 'torch'
$env:XDG_CACHE_HOME = $IopaintCache
$env:HF_HOME        = Join-Path $IopaintCache 'huggingface'
```

These are set before launching IOPaint and cleared after, so they do not bleed
into the main app. The `lama` model (~200MB) downloads into
`data/iopaint-cache/torch/hub/checkpoints/` on first launch; subsequent starts
load it from disk.

**Avoid it.** Any tool that calls `torch.hub` or `huggingface_hub` on Windows
assumes `~/.cache` is writable. Under OneDrive folder redirection it may not
be. Setting `TORCH_HOME` and `HF_HOME` to a project-local directory is the
reliable fix — and it keeps the model weights with the project rather than
scattering them in the user profile.

---

## DeepMosaic's error responses crashed the worker with TypeError

**Symptom.** A DeepMosaic job fails (e.g. models not downloaded), and the worker
returns nothing — not a 500, not a JSON error, just a connection reset. The main
app reports `remote 500: ` with an empty body.

**Cause.** `docker/deepmosaic/server.py` used:

```python
return JSONResponse(
    status_code=500,
    detail=f"deepmosaic.py not found at {DEEPMOSAIC_SCRIPT}",
)
```

`JSONResponse` is a Starlette class whose `__init__` signature is
`__init__(self, content, status_code=200, headers=None, media_type=None)`. It
has **no** `detail` parameter — that belongs to `HTTPException`. Passing
`detail=` as a keyword argument raises `TypeError: __init__() got an unexpected
keyword argument 'detail'`, and since this happens inside the error handler
itself, the exception propagates up and uvicorn resets the connection. Every
error path in the worker — missing script, processing timeout, non-zero exit,
no output file — had the same bug.

**Why it hid.** The four `JSONResponse(... detail=...)` calls look correct at a
glance — `detail` is the conventional FastAPI error field, and `HTTPException`
uses it. But `JSONResponse` is a raw response class, not an exception. The
difference is invisible until an error actually occurs, and the worker starts
and serves `/status` correctly because the success path never constructs a
`JSONResponse`. Only the failure path crashes, and the failure path is the one
you test last.

**Fix.** All four calls now use `content={"detail": "..."}`:

```python
return JSONResponse(
    status_code=500,
    content={"detail": f"deepmosaic.py not found at {DEEPMOSAIC_SCRIPT}"},
)
```

The main app reads the error via `resp.text`, so the body format is compatible.

**Avoid it.** `JSONResponse` and `HTTPException` are both in `fastapi.responses`
/ `fastapi` and both deal with HTTP errors, but their constructors are
different. `HTTPException(status_code, detail)` raises; `JSONResponse(content,
status_code)` returns. Mixing their parameter names is a silent bug because the
success path never calls the error constructor.

---

## DeepMosaics was an empty directory — the submodule never initialised

**Symptom.** The DeepMosaic worker starts and `/status` returns
`{"available": false}`, even though the `DeepMosaics/` directory exists. Every
`/process` request returns 500: `deepmosaic.py not found`.

**Cause.** The project was downloaded as a ZIP from GitHub, not cloned with
`git clone --recursive`. The `.git` directory is absent, so
`git submodule update --init DeepMosaics` fails with `fatal: not a git
repository`. The `DeepMosaics/` directory exists in the ZIP (because
`.gitmodules` references it) but is empty — submodules are not included in
GitHub ZIP downloads.

**Why it hid.** The setup script ran `git submodule update --init DeepMosaics`
and printed nothing — the `fatal: not a git repository` error went to stderr,
which was not checked. The directory `DeepMosaics/` existed (empty), so
`Test-Path` returned true and the script assumed the submodule was present.
Only the worker's `/status` endpoint, which checks for `deepmosaic.py` inside
the directory, revealed that the directory was a shell.

**Fix.** The setup script now checks for `.git` and falls back to a direct
clone:

```powershell
if (Test-Path (Join-Path $Root '.git')) {
    & git submodule update --init DeepMosaics
} else {
    & git clone https://github.com/HypoX64/DeepMosaics.git $DmDir
}
```

And it checks for `deepmosaic.py` specifically, not just the directory.

**Avoid it.** A submodule directory exists in a ZIP download but is empty.
`Test-Path` on the directory returns true; only `Test-Path` on a file *inside*
it reveals the truth. Always check for the file you need, not the directory
that should contain it. And `git submodule` silently fails outside a git repo
— check `$LASTEXITCODE`.

---

## DeepMosaic's worker had no `process_video` method — video uploads crashed

**Symptom.** Uploading an image to DeepMosaic works. Uploading a video crashes
the main app with `AttributeError: 'DeepMosaicService' object has no attribute
'process_video'`.

**Cause.** `DeepMosaicService` in `api/main.py` defined `process_image()` but
not `process_video()`. The endpoint that handles multipart uploads dispatches
on content type and calls `process_video()` for video files. The method was
never defined — only `process_image` existed in the class. In local mode the
worker subprocess handles both; in remote mode the main app's class is the only
interface, and it was incomplete.

**Why it hid.** Image uploads work, so the DeepMosaic feature appears
functional. Video is a separate code path that is only exercised when a user
actually uploads a `.mp4`. The endpoint's `if content_type.startswith("video")`
branch is unreachable in testing without a video file, and the `AttributeError`
is not raised until that branch runs.

**Fix.** Added `process_video()` to `DeepMosaicService` that delegates to
`_remote_process()` in remote mode (same as `process_image`), and runs the
local subprocess path for the non-remote case.

**Avoid it.** When an endpoint dispatches to two methods on a service class,
both methods must exist — even if one is a stub. `AttributeError` on a missing
method is not a graceful degradation; it is a crash. An abstract interface with
one concrete implementation is a bug waiting for the other input type.

---

## The PID tracker wrote nested JSON and could not stop the processes

**Symptom.** `start-social-hunt.ps1 -Stop` prints "Killing..." for a process
that is already dead, and the PID file grows with each restart until it contains
nested `{"value": [...], "Count": N}` wrappers that `Stop-Tracked` cannot
iterate.

**Cause.** `Save-Pid` used:

```powershell
$list = @()
if (Test-Path $PidFile) {
    $list = @(Get-Content $PidFile | ConvertFrom-Json)
}
$list += [pscustomobject]@{ name = $name; pid = $procId }
```

When the JSON file contains a single object (not an array), `ConvertFrom-Json`
returns a `PSCustomObject`, not an array. Wrapping it in `@()` produces a
one-element array, but `+=` on an array with a `PSCustomObject` can cause
PowerShell to unwrap and re-wrap the collection depending on the pipeline
context. Over multiple runs the file accumulated `value`/`Count` properties
from PowerShell's internal array representation, producing a structure like:

```json
[{"value": [{"name": "deepmosaic", "pid": 26768}], "Count": 1},
 {"name": "social-hunt", "pid": 36020}]
```

`Stop-Tracked` iterated the top-level array, found `value` (not `pid`) on the
first element, and skipped it — the process was never killed.

**Why it hid.** The first run worked (empty file, fresh array). The second run
corrupted the file (single-object deserialization + array unwrap). The third run
failed to stop anything. The bug is in the serialization, not the process
management, so `Get-Process` showed the orphaned processes but the script
could not reach them.

**Fix.** `Save-Pid` uses a `List[pscustomobject]` and serialises with
`ToArray()`, which produces a clean JSON array regardless of element count.
`Get-TrackedPids` normalises both single-object and array deserialisation:

```powershell
$raw = Get-Content $PidFile -Raw | ConvertFrom-Json
if ($raw -is [array]) { return $raw } else { return @($raw) }
```

**Avoid it.** `ConvertFrom-Json` returns a single object for a one-element
array and an array for a multi-element one. Any code that iterates the result
must normalise first — `@()` is not enough when `+=` is involved, because
PowerShell's array addition can create `value`/`Count` wrapper objects from
internal collection types. Use `[List[T]]` and `ToArray()` for deterministic
serialisation.

---

## The demask pix2pix fallback had a duplicate keyword argument

**Symptom.** A demask request using the pix2pix fallback model crashes the
backend with `SyntaxError: keyword argument repeated`.

**Cause.** The pix2pix configuration block in `api/main.py` listed
`image_guidance_scale` twice in the same dict literal — once at the top of the
block and once in the fallback branch. Python raises `SyntaxError` at import
time for duplicate keyword arguments in function calls, but a dict literal with
a duplicate key silently keeps the last value at runtime. In this case the
duplicate was in a dict construction passed to a Replicate API call, and the
Replicate client raised it as a `TypeError`.

**Why it hid.** The primary demask path (Replicate's main model) does not use
the fallback, so the duplicate key is only hit when the primary model is
unavailable. The error message points at the Replicate client, not at the dict
construction, so it reads like an API issue rather than a typo.

**Fix.** Removed the duplicate `image_guidance_scale` key from the fallback
branch.

**Avoid it.** Dict literals with duplicate keys are valid Python syntax but
silently discard earlier values. A linter with duplicate-key detection (ruff's
`DUO103`, pylint's `W0123`) catches this; without one, the bug only surfaces at
the call site that uses the discarded key.

---

## The IOPaint UI was proxied under /iopaint/ — a path it was never built for

**Symptom.** Clicking "Open IOPaint WebUI" from the dashboard loads a broken
page: the HTML renders but all CSS, JS, and API calls 404, because the browser
requests `/iopaint/assets/app.js` while IOPaint internally serves
`/assets/app.js`.

**Cause.** `nginx.conf` proxied `/iopaint/` to `iopaint:8080/`, and the
frontend's `openIOPaint()` opened `/iopaint/` in a new tab. IOPaint's web UI is
a single-page app that assumes it is served at the site root. Its internal
asset paths (`/assets/`, `/api/`) are absolute, not relative to a subpath. When
served under `/iopaint/`, the browser resolves `/assets/app.js` against the
site root (not `/iopaint/assets/`), and nginx routes those to Social-Hunt,
which has no `/assets/` endpoint.

Separately, the global `/api/` proxy in nginx bled into Social-Hunt's
namespace — Social-Hunt uses `/sh-api/` for its API, but `/api/` was proxied to
IOPaint, causing route interference.

**Why it hid.** The HTML loads (it's served at `/iopaint/`), so the page
appears to work. Only the assets fail, and they fail with 404s that look like
missing files rather than a routing problem. The IOPaint container is healthy
and responds on port 8080 directly; the failure is only in the proxied path.

**Fix.** Removed the `/iopaint/` proxy from `nginx.conf` entirely. IOPaint's UI
is now opened directly on its own port: `openIOPaint()` navigates to
`http://<host>:8080/`, a separate origin with no path rewriting. The global
`/api/`, `/assets/`, `/socket.io/` proxies were also removed — Social-Hunt's
`/sh-api/` is the only API path nginx needs to route.

**Avoid it.** A single-page app that uses absolute asset paths cannot be served
under a subpath without rewriting every internal URL. The reliable approach is
a separate origin (different port), not a subpath proxy. And a reverse proxy
that routes `/api/` globally will collide with any backend that also uses
`/api/` — scope your proxy paths to the specific backend's prefix.

---

## Smaller ones

- **`python-multipart` missing from DeepMosaic venv.** The worker's FastAPI
  routes use `UploadFile = File(...)` and `Form(...)`, which import
  `python-multipart` at route-definition time. Without it the server crashes on
  import with `RuntimeError: Form data requires "python-multipart"`. The
  package is not a transitive dependency of FastAPI — it must be listed
  explicitly. Added to `setup-ai.ps1`'s deepmosaic install line.

- **`server.py` had hardcoded Linux paths.** `DEEPMOSAIC_DIR` defaulted to
  `/app/DeepMosaics` and results to `/tmp/deepmosaic_results`. On Windows those
  are not writable. The defaults now branch on `os.name`: `/app/` and `/tmp/`
  on Linux, `%TEMP%` and the project-relative `DeepMosaics/` on Windows. The
  env-var override still takes precedence.

- **DeepMosaic `check_models` / `apply_compat_patches` crashed in remote mode.**
  These methods assumed `self.deepmosaic_dir` was a real path and called
  `os.listdir()` on it. In remote mode `deepmosaic_dir` is `None`. They now
  return early when `self.remote` is set.

- **Traditional DeepMosaic mode is dead code.** The UI option for "traditional"
  quality is commented out in `web/views/deepmosaic.html`, and the backend
  branch for `quality == "traditional"` is unreachable. Known, not blocking —
  the "medium" and "high" quality paths work.