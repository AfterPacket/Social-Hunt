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

## DeepMosaic crashed with `remote 500` because the models never downloaded

**Cause:** Two compounding bugs.

1. `scripts/setup-ai.ps1` piped a stream of `n` answers to
   `download_deepmosaic_models.py`. The downloader's **first** prompt is
   `Do you want to continue? (y/n):` — answering `n` aborts immediately, so
   **zero** model files were ever fetched. `DeepMosaics/pretrained_models/`
   contained only the 28-byte `put_pretrained_model_here` placeholder.

2. When a model was missing, `deepmosaic.py` / `cores/options.py` called
   `input('Please press any key to exit.\n')`. The worker launches the
   subprocess with `stdin=asyncio.subprocess.DEVNULL`; under a closed stdin
   `input()` raises an **uncaught** `EOFError`, so Python exits with code 1
   instead of the intended `sys.exit(0)`. The worker surfaced this as a bare
   `DeepMosaic failed (exit 1): Traceback ...` with no indication that the
   actual problem was missing model weights.

**Fixes:**

- `download_deepmosaic_models.py` now accepts `--yes` / `-y` which auto-answers
  every prompt via an `ask()` helper (and falls back to the default on
  `EOFError` for true no-stdin environments). `setup-ai.ps1` calls it with
  `--yes`. The dead `catbox.moe` mirror URLs were replaced with the official
  Google Drive file IDs used by `gdown`, so models actually download.

- `DeepMosaics/cores/options.py` and `DeepMosaics/deepmosaic.py`: every
  `input('Please press any key to exit.\n')` replaced with `print()` +
  `sys.exit(1)`. The worker now returns a clear `Error: Model does not exist!`
  message instead of a truncated traceback.

- `docker/deepmosaic/server.py` now pre-checks model presence for the
  requested `mode` **before** spawning the subprocess and returns a clean 500
  with the message `DeepMosaic models are not downloaded. Run\n  python download_deepmosaic_models.py --yes`.

## Model filename mismatch between server and Google Drive

**Cause:** The worker's `_models_present()` and model-selection logic checked
for `clean_youknow_v1.pth` and `style/candy.pth`, but the official DeepMosaics
Google Drive folder ships `clean_youknow_resnet_9blocks.pth` and
`style/edges2cat.pth`. Even after a successful download the worker reported
the models as missing.

**Fix:** Updated `_models_present()`, the `/process` model-selection blocks, and
the `DeepMosaicService` class in `api/main.py` to look for the real filenames
(`clean_youknow_resnet_9blocks.pth`, `edges2cat.pth`).

## Demask endpoint crashed with "cannot identify image file <_io.BytesIO object>"

**Cause:** `PIL.Image.open(BytesIO(content))` in `_generate_face_coverage_mask`
raises `UnidentifiedImageError` when the upload isn't a valid image (empty,
corrupted, or wrong MIME type). The error bubbled up as a raw 500 with a
cryptic traceback referencing a memory address.

**Fix:** `api/main.py` `/sh-api/demask` now validates the upload with
`Image.open(BytesIO(content)).verify()` before any processing and returns a
clear 400 `Cannot identify image file. Please upload a valid JPEG, PNG, WebP,
or BMP image.`

## `rarfile` import crash in download_deepmosaic_models.py

**Cause:** `import rarfile` was at module top level, so the script crashed
before `install_rarfile()` could ever run when the package wasn't installed.

**Fix:** The top-level import was removed; `_ensure_rarfile()` now installs
and imports it lazily inside `main()`. `gdown` was added to the deepmosaic
venv's dependency list in `setup-ai.ps1`.

## DeepMosaic crashed with `RuntimeError` loading state_dict (missing/extra keys)

**Cause:** `DeepMosaics/models/loadmodel.py` calls `load_state_dict()` without
`strict=False` in four places: `pix2pix()`, `style()`, `video()`, and
`bisenet()` (two calls — roi and mosaic_position). The upstream checkpoints
(`clean_face_HD.pth`, `mosaic_position.pth`, `add_face.pth`, etc.) were
saved with older PyTorch and contain key mismatches (extra buffers like
`num_batches_tracked`, or renamed keys) under torch >= 2.x. Without
`strict=False` the loader raises `RuntimeError: Error(s) in loading state_dict
for ...: Missing key(s) ... / Unexpected key(s) ...` and the whole `/process`
job crashes with exit 1.

The `apply_compat_patches()` method in `api/main.py` was designed to patch
`loadmodel.py` at runtime, but it has an early return in remote mode
(`if self.remote: return`). The non-Docker deploy uses remote mode (loopback
HTTP to the worker), so the patches were never applied. Even in local mode,
`apply_compat_patches()` only patched the `style()` `netG.load_state_dict
(state_dict)` call and the `model_util.py` InstanceNorm helper — it missed the
`pix2pix()`, `video()`, and both `bisenet()` calls.

**Fix:**

- `DeepMosaics/models/loadmodel.py`: added `strict=False` to all four
  `load_state_dict()` call sites (lines 22, 47, 56, 68, 70). The `strict=False`
  flag tells PyTorch to silently drop unexpected keys and leave missing keys at
  their initialised values, which is correct for inference with these legacy
  checkpoints.

- `scripts/setup-ai.ps1`: added a post-clone patch block that re-applies the
  `strict=False` edits to `loadmodel.py` after every fresh clone. Because
  `DeepMosaics/` is `.gitignore`d (it's a submodule), the patched file is not
  versioned and must be re-patched on every setup. The patch covers all four
  call sites (pix2pix, style, video, bisenet roi, bisenet mosaic_position).

- `docker/deepmosaic/server.py`: error truncation increased from 500 to 2000
  chars, and the full failure output is now printed to the worker's stdout so
  the root cause is visible in `data/logs/deepmosaic-stdout.log` instead of
  being cut off mid-traceback.

## IOPaint WebUI "cannot identify image file <_io.BytesIO object>"

**Cause:** The IOPaint 1.6.0 WebUI frontend sometimes sends an empty or
 corrupted multipart upload to its own `/api/v1/gen-info` endpoint. The
 `api_geninfo` handler in `iopaint/api.py` calls `load_img(file.file.read())`
 unconditionally; when `file.file.read()` returns empty bytes,
 `Image.open(io.BytesIO(b''))` raises `UnidentifiedImageError` and the whole
 request 500s. The error message `cannot identify image file <_io.BytesIO
 object at 0x...>` surfaces in the browser with no hint that the upload was
 empty. The actual inpainting endpoint (`/api/v1/inpaint`) works fine via
 direct API calls — only the metadata-extraction step crashes.

**Fix:**

- `iopaint/api.py` (in `.venv-iopaint`, patched by `setup-ai.ps1` after
  install): `api_geninfo` now reads `file.file.read()` into a local variable,
  returns an empty `GenInfoResponse` on empty data, and wraps `load_img` in a
  try/except that returns empty prompt info on any decode failure. This lets
  the upload flow continue to the inpaint step instead of crashing.

- `scripts/setup-ai.ps1`: added a post-install patch block (using a temp
  Python script) that re-applies the `api_geninfo` guard after every IOPaint
  install, since the wheel is not editable in git.

- `web/views/iopaint.html`: the "Open IOPaint WebUI" button was opening
  `/iopaint/?v=...` on the Social-Hunt port (8000), which returned 404 — there
  is no IOPaint proxy route. It now opens `http://127.0.0.1:<port>/?v=...`
  directly on the IOPaint server's own port, where the WebUI's absolute
  requests to `/api/v1/...` and `/socket.io/...` resolve correctly.

## DeepMosaic returned the original image unchanged ("people not demasked")

**Cause:** Two compounding issues:

1. CMYK / progressive JPEGs: the user's `original (1).jpg` was a CMYK JPEG.
   PIL reads it fine (the main app validates with PIL), but `cv2.imdecode`
   (used by DeepMosaics' `impro.imread`) returns `None` for CMYK JPEGs.
   That `None` propagated to `runmodel.get_mosaic_position` as
   `'NoneType' object has no attribute 'shape'`.

2. DeepMosaic's **Clean** mode removes **digital mosaic pixelation**
   (Japanese-style censorship blur), not physical face coverings (masks,
   balaclavas, gaiters). When no mosaic pixelation is detected (the
   segmentation model returns `size <= 100`), it prints `Do not find mosaic`
   and saves the original image unchanged. Users uploading images with
   physical face coverings and expecting demasking should use the **Demask**
   feature (Replicate SD inpainting), not DeepMosaic's Clean mode.

**Fix:**

- `docker/deepmosaic/server.py`: uploads are now normalized to a standard
  RGB JPEG via `PIL.Image.open().convert('RGB')` before being saved for the
  subprocess. This fixes CMYK, progressive JPEG, WebP, BMP, TIFF, and RGBA
  PNG inputs — `cv2.imdecode` always succeeds on the normalized output.

- `DeepMosaics/cores/clean.py` (patched by `setup-ai.ps1`): added a guard
  after `impro.imread(path)` that raises a clear `RuntimeError` if the image
  is `None`, instead of the cryptic `'NoneType' object has no attribute
  'shape'` traceback.

## IOPaint `/api/v1/inpaint` 500: cannot identify image file (empty base64)

**Cause:** The same IOPaint 1.6.0 WebUI frontend bug that affects
`/api/v1/gen-info` also affects `/api/v1/inpaint`. When the user clicks
“Inpaint” before the canvas image is fully loaded (or with a large image
that the canvas struggles with), the frontend sends empty or truncated
base64 to the inpaint endpoint. `decode_base64_to_image()` in
`iopaint/helper.py` calls `Image.open(io.BytesIO(image_bytes))` without
validating the input, so empty/corrupted bytes raise
`UnidentifiedImageError: cannot identify image file <_io.BytesIO object>`
and the request crashes with 500.

Large images are especially affected: the WebUI canvas `toDataURL()`
produces a very large base64 string that can be truncated during the
HTTP transfer, producing bytes that `Image.open` cannot decode.

**Fix:**

- `iopaint/helper.py` (patched by `setup-ai.ps1`): `decode_base64_to_image`
  now guards against `None`/empty encoding, strips the data URL prefix
  safely, validates `base64.b64decode` in a try/except, and checks for empty
  decoded bytes — raising a clear `ValueError` at each step instead of
  falling through to `Image.open` with invalid data.

- `iopaint/api.py` (patched by `setup-ai.ps1`): `api_inpaint` wraps the two
  `decode_base64_to_image` calls (image + mask) in a try/except that returns
  HTTP 400 with a clear message (`Invalid image or mask data: ...`) instead
  of letting the exception crash the request with a 500.

  Both patches are re-applied by `setup-ai.ps1` after every IOPaint install
  because the wheel is not editable in git.

**Note on demasking:** IOPaint's default `lama` model is an **object removal**
model — it fills the masked area with background pixels, which is why masking
a face and running lama produces a blurred/background result instead of a
reconstructed face. For **face reconstruction** (demasking physical face
coverings), use either:
  - Social-Hunt's **Demask** feature (Replicate SD inpainting with a face
    prompt), or
  - IOPaint with a **diffusion model** (e.g. `runwayml/stable-diffusion-inpainting`)
    and a prompt like “a face”. This is much slower on CPU than lama and
    requires downloading the 4GB+ SD model.

DeepMosaic's **Clean** mode removes **digital mosaic pixelation**
(Japanese-style censorship blur), not physical face coverings. It will return
the image unchanged if no mosaic pixelation is detected.

## IOPaint 400: cannot identify image file (AVIF image with a .jpg extension)

**Cause:** The user's upload `original (1).jpg` was actually an **AVIF** file
(magic bytes `ftypavif` at offset 4), despite the `.jpg` extension. Browsers
and phone cameras increasingly save AVIF images with a `.jpg` extension. The
IOPaint WebUI canvas renders the image fine (browsers have native AVIF
support), but the backend `decode_base64_to_image()` calls
`Image.open(io.BytesIO(avif_bytes))`, and **Pillow 9.5.0** (the version pinned
by `iopaint==1.6.0`) **does not support AVIF**. `Image.open` raises
`UnidentifiedImageError`, which surfaced in the browser as:

```
400: Invalid image or mask data: cannot identify image file <_io.BytesIO object at 0x...>
```

The 400 (not 500) is from the `api_inpaint` try/except guard added in the
previous fix — without that guard it would have been a 500 crash. The error
message does not name AVIF because Pillow's `UnidentifiedImageError` does not
report the file magic bytes.

**Why it hid:** The `.jpg` extension is a lie. Every tool that inspects the
extension (the OS, the browser file picker, the WebUI canvas) reports "JPEG",
so AVIF is never suspected. The bug only appears in the backend where Pillow
parses the actual bytes. Adding debug logging to `decode_base64_to_image`
(revealing `first_bytes=b'\x00\x00\x00 ftypavif...'`) was what identified the
root cause.

**Fix:**

- `scripts/setup-ai.ps1`: installs `pillow-avif-plugin` into `.venv-iopaint`
  immediately after `iopaint==1.6.0`. The plugin registers itself on `PIL`
  import and adds an AVIF decoder to Pillow 9.5.0. It must be installed AFTER
  iopaint (which pins Pillow) so it binds to the pinned version.

  **Installing the package alone is not enough.** `pillow-avif-plugin` needs
  an explicit `import pillow_avif` to call `Image.register_open()` for `.avif`;
  IOPaint never imports it, so the package can be installed and AVIF still
  fails. `setup-ai.ps1` writes a `.pth` file (`zz_pillow_avif.pth`) into the
  venv's site-packages containing `import pillow_avif`. `site.py` executes
  `import` lines in `.pth` files at every interpreter startup, so the plugin
  auto-loads before IOPaint touches PIL.

- `iopaint/helper.py` (patched by `setup-ai.ps1`): `decode_base64_to_image`
  now wraps `Image.open` in a try/except that includes `bytes_len` and the
  first 16 bytes (hex) in the error message. Future unsupported-format issues
  will surface their magic bytes in the 400 response instead of the generic
  `UnidentifiedImageError`.