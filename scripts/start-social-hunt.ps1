<#
.SYNOPSIS
  Starts Social-Hunt plus its two isolated AI workers (IOPaint, DeepMosaic)
  locally on Windows without Docker. Each runs in its own console window using
  its dedicated venv created by scripts/setup-ai.ps1.

.DESCRIPTION
  - Social-Hunt (port 8000)      -> .venv            (secure Pillow 12)
  - IOPaint   (port 8080)        -> .venv-iopaint    (Pillow 9.5 / torch 2.1.2)
  - DeepMosaic worker (port 8081)-> .venv-deepmosaic (torch 2.1.2)

  The main app is launched with IOPAINT_URL and DEEPMOSAIC_URL env vars so it
  talks to the sibling workers over loopback instead of trying to spawn them as
  subprocesses. This is the exact same remote-mode wiring the docker-compose
  `ai` profile uses, just with local processes instead of containers.

  Use -NoIOPaint / -NoIOPaintSD / -NoDeepMosaic to skip a worker. Use -Stop to
  kill the processes started by this script (tracked in data/.ai-pids.json).

.PARAMETER Stop
  Stop any Social-Hunt / IOPaint / DeepMosaic processes previously started by
  this script, then exit.

.PARAMETER NoIOPaint
  Do not start the IOPaint worker.

.PARAMETER NoIOPaintSD
  Do not start the IOPaint SD (demask) worker on :8082.

.PARAMETER NoDeepMosaic
  Do not start the DeepMosaic worker.

.EXAMPLE
  pwsh scripts/start-social-hunt.ps1
  pwsh scripts/start-social-hunt.ps1 -Stop
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$NoIOPaint,
    [switch]$NoIOPaintSD,
    [switch]$NoDeepMosaic
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Force UTF-8 for Python stdout/stderr so emoji / unicode in run.py and the AI
# workers don't crash with cp1252 UnicodeEncodeError in new console windows.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

# --- helpers ------------------------------------------------------------------
$PidFile = Join-Path $Root 'data\.ai-pids.json'

function Get-TrackedPids {
    if (-not (Test-Path $PidFile)) { return @() }
    try {
        $raw = Get-Content $PidFile -Raw | ConvertFrom-Json
        # ConvertFrom-Json returns a single object for a 1-element array;
        # wrap in @() to normalise.
        if ($raw -is [array]) { return $raw } else { return @($raw) }
    } catch { return @() }
}

function Stop-Tracked {
    $pids = Get-TrackedPids
    foreach ($entry in $pids) {
        try {
            $null = Get-Process -Id $entry.pid -ErrorAction Stop
            Write-Host "[stop] Killing $($entry.name) (pid $($entry.pid))" -ForegroundColor Yellow
            Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
        } catch {
            # already gone
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Save-Pid($name, $procId) {
    $list = [System.Collections.Generic.List[pscustomobject]]::new()
    foreach ($e in (Get-TrackedPids)) { $list.Add($e) }
    $list.Add([pscustomobject]@{ name = $name; pid = $procId })
    $list.ToArray() | ConvertTo-Json -Depth 5 | Set-Content $PidFile -Encoding UTF8
}

# --- stop mode ----------------------------------------------------------------
if ($Stop) {
    Write-Host '[stop] Stopping tracked AI workers + Social-Hunt ...' -ForegroundColor Yellow
    Stop-Tracked
    Write-Host '[stop] Done.' -ForegroundColor Green
    return
}

Write-Host ''
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host '   Social-Hunt + AI workers (non-Docker local)'      -ForegroundColor Cyan
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host "Project root: $Root"
Write-Host ''

# --- verify venvs -------------------------------------------------------------
$MainPy   = Join-Path $Root '.venv\\Scripts\\python.exe'
$IopaintPy = Join-Path $Root '.venv-iopaint\\Scripts\\python.exe'
$DmPy     = Join-Path $Root '.venv-deepmosaic\\Scripts\\python.exe'

if (-not (Test-Path $MainPy)) {
    Write-Host '[error] Main .venv missing. Run:' -ForegroundColor Red
    Write-Host '        py -3.11 -m venv .venv ; .\\.venv\\Scripts\\Activate.ps1 ; pip install -r requirements.txt' -ForegroundColor Yellow
    exit 1
}

if (-not $NoIOPaint -and -not (Test-Path $IopaintPy)) {
    Write-Host '[error] .venv-iopaint missing. Run scripts/setup-ai.ps1 first.' -ForegroundColor Red
    exit 1
}

if (-not $NoDeepMosaic -and -not (Test-Path $DmPy)) {
    Write-Host '[error] .venv-deepmosaic missing. Run scripts/setup-ai.ps1 first.' -ForegroundColor Red
    exit 1
}

# Make sure no stale tracked processes are running before we start fresh.
Stop-Tracked

# Create a logs directory for the background services.
$LogDir = Join-Path $Root 'data\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --- 1) DeepMosaic worker (port 8081) -----------------------------------------
if (-not $NoDeepMosaic) {
    $ServerPy = Join-Path $Root 'docker\deepmosaic\server.py'
    if (-not (Test-Path $ServerPy)) {
        Write-Host '[error] docker/deepmosaic/server.py not found.' -ForegroundColor Red
        exit 1
    }
    Write-Host '[1/3] Starting DeepMosaic worker on :8081 ...'
    # DEEPMOSAIC_DIR points at the DeepMosaics dir so server.py finds deepmosaic.py +
    # pretrained_models. Results/temp dirs default to %TEMP% on Windows.
    $env:DEEPMOSAIC_DIR = Join-Path $Root 'DeepMosaics'
    $DmOut = Join-Path $LogDir 'deepmosaic-stdout.log'
    $DmErr  = Join-Path $LogDir 'deepmosaic-stderr.log'
    # Quote the script path (project path has a space + parens). Start-Process
    # -ArgumentList splits on spaces; using a single quoted string avoids that.
    $proc = Start-Process -FilePath $DmPy -ArgumentList "`"$ServerPy`"" `
        -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $DmOut -RedirectStandardError $DmErr
    Save-Pid 'deepmosaic' $proc.Id
    # Clear this worker-specific env so it doesn't bleed into the main app.
    Remove-Item Env:DEEPMOSAIC_DIR -ErrorAction SilentlyContinue
    Write-Host "      pid $($proc.Id) -> http://127.0.0.1:8081/status" -ForegroundColor DarkGray
    Write-Host "      logs: $DmErr" -ForegroundColor DarkGray
}

# --- 2) IOPaint worker (port 8080) --------------------------------------------
if (-not $NoIOPaint) {
    Write-Host '[2/3] Starting IOPaint WebUI on :8080 ...'
    # IOPaint/torch needs a writable cache dir. The default (~/.cache) can be
    # permission-denied on some Windows setups, so we redirect it into the
    # project tree. Start-Process inherits $env:, so we set them here and
    # clear them after launch so they don't bleed into the main app.
    $IopaintCache = Join-Path $Root 'data\iopaint-cache'
    New-Item -ItemType Directory -Force -Path $IopaintCache | Out-Null
    $env:TORCH_HOME     = Join-Path $IopaintCache 'torch'
    $env:XDG_CACHE_HOME = $IopaintCache
    $env:HF_HOME        = Join-Path $IopaintCache 'huggingface'

    # `iopaint` is a console script installed by the iopaint wheel.
    $IopaintExe = Join-Path $Root '.venv-iopaint\Scripts\iopaint.exe'
    $IoOut = Join-Path $LogDir 'iopaint-stdout.log'
    $IoErr  = Join-Path $LogDir 'iopaint-stderr.log'
    $ioArgs = 'start --host 127.0.0.1 --port 8080 --device cpu'
    if (-not (Test-Path $IopaintExe)) {
        # Fallback: invoke via python -m
        $proc = Start-Process -FilePath $IopaintPy `
            -ArgumentList "-m iopaint $ioArgs" `
            -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $IoOut -RedirectStandardError $IoErr
    } else {
        $proc = Start-Process -FilePath $IopaintExe `
            -ArgumentList $ioArgs `
            -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $IoOut -RedirectStandardError $IoErr
    }
    Save-Pid 'iopaint' $proc.Id
    Write-Host "      pid $($proc.Id) -> http://127.0.0.1:8080/" -ForegroundColor DarkGray
    Write-Host '      (first launch downloads the lama model ~200MB, be patient)' -ForegroundColor DarkGray
    Write-Host "      logs: $IoErr" -ForegroundColor DarkGray
    # Clear IOPaint cache env so it doesn't bleed into the main app.
    Remove-Item Env:TORCH_HOME     -ErrorAction SilentlyContinue
    Remove-Item Env:XDG_CACHE_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:HF_HOME        -ErrorAction SilentlyContinue
}

# 2b) IOPaint SD worker (port 8082) for demasking
# A second IOPaint instance dedicated to SD inpainting for the Demask feature.
# Uses Sanster/Realistic_Vision_V1.4-inpainting (photorealistic SD 1.5 fine-tune,
# the local equivalent of the Replicate model). Runs on GPU (--device cuda) so
# SD inference is ~10-30s on a 4090. The lama IOPaint on :8080 stays on CPU for
# object-removal in the WebUI. Skip with -NoIOPaintSD.
if (-not $NoIOPaint -and -not $NoIOPaintSD) {
    Write-Host '[2b/3] Starting IOPaint SD (demask) on :8082 ...'
    $IopaintCache = Join-Path $Root 'data\iopaint-cache'
    New-Item -ItemType Directory -Force -Path $IopaintCache | Out-Null
    $env:TORCH_HOME     = Join-Path $IopaintCache 'torch'
    $env:XDG_CACHE_HOME = $IopaintCache
    $env:HF_HOME        = Join-Path $IopaintCache 'huggingface'

    $IopaintExe = Join-Path $Root '.venv-iopaint\Scripts\iopaint.exe'
    $IoSdOut = Join-Path $LogDir 'iopaint-sd-stdout.log'
    $IoSdErr  = Join-Path $LogDir 'iopaint-sd-stderr.log'
    # The SD safety checker can classify a realistic face reconstruction as a
    # false-positive and return a completely black image. This worker is used
    # only for the explicitly selected demasking crop, so disable that checker
    # here; the API still rejects blank/invalid outputs before compositing.
    $ioSdArgs = 'start --host 127.0.0.1 --port 8082 --device cuda --model Sanster/Realistic_Vision_V1.4-inpainting --disable-nsfw-checker'
    if (-not (Test-Path $IopaintExe)) {
        $proc = Start-Process -FilePath $IopaintPy -ArgumentList "-m iopaint $ioSdArgs" -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $IoSdOut -RedirectStandardError $IoSdErr
    } else {
        $proc = Start-Process -FilePath $IopaintExe -ArgumentList $ioSdArgs -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $IoSdOut -RedirectStandardError $IoSdErr
    }
    Save-Pid 'iopaint-sd' $proc.Id
    Write-Host "      pid $($proc.Id) -> http://127.0.0.1:8082/" -ForegroundColor DarkGray
    Write-Host '      (first launch downloads the SD model ~4GB, be patient)' -ForegroundColor DarkGray
    Write-Host "      logs: $IoSdErr" -ForegroundColor DarkGray
    Remove-Item Env:TORCH_HOME     -ErrorAction SilentlyContinue
    Remove-Item Env:XDG_CACHE_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:HF_HOME        -ErrorAction SilentlyContinue
}

# --- 3) Social-Hunt main app (port 8000) --------------------------------------
Write-Host '[3/3] Starting Social-Hunt on :8000 ...'
$RunPy = Join-Path $Root 'run.py'
if (-not (Test-Path $RunPy)) {
    Write-Host '[error] run.py not found at project root.' -ForegroundColor Red
    exit 1
}

# Tell the main app to talk to the sibling workers over loopback instead of
# spawning subprocesses. This is the same remote-mode wiring as docker-compose.
# Start-Process inherits the current $env: block, so we set them here.
if (-not $NoIOPaint)    { $env:IOPAINT_URL    = 'http://127.0.0.1:8080' }
if (-not $NoDeepMosaic) { $env:DEEPMOSAIC_URL = 'http://127.0.0.1:8081' }
if (-not $NoIOPaint -and -not $NoIOPaintSD) { $env:IOPAINT_SD_URL = 'http://127.0.0.1:8082' }

$ShOut = Join-Path $LogDir 'social-hunt-stdout.log'
$ShErr  = Join-Path $LogDir 'social-hunt-stderr.log'
$proc = Start-Process -FilePath $MainPy -ArgumentList "`"$RunPy`"" `
    -WorkingDirectory $Root -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $ShOut -RedirectStandardError $ShErr
Save-Pid 'social-hunt' $proc.Id
Write-Host "      pid $($proc.Id) -> http://127.0.0.1:8000" -ForegroundColor DarkGray
Write-Host "      logs: $ShErr" -ForegroundColor DarkGray

# Clear the loopback URL env vars we set for the main app.
Remove-Item Env:IOPAINT_URL    -ErrorAction SilentlyContinue
Remove-Item Env:DEEPMOSAIC_URL -ErrorAction SilentlyContinue
Remove-Item Env:IOPAINT_SD_URL -ErrorAction SilentlyContinue

# --- summary ------------------------------------------------------------------
Write-Host ''
Write-Host '==================================================' -ForegroundColor Green
Write-Host ' All services starting in background (hidden)'      -ForegroundColor Green
Write-Host '==================================================' -ForegroundColor Green
Write-Host ''
Write-Host '  Social-Hunt    : http://127.0.0.1:8000' -ForegroundColor White
if (-not $NoIOPaint)    { Write-Host '  IOPaint WebUI  : http://127.0.0.1:8080' -ForegroundColor White }
if (-not $NoIOPaint -and -not $NoIOPaintSD) { Write-Host '  IOPaint SD (demask): http://127.0.0.1:8082' -ForegroundColor White }
if (-not $NoDeepMosaic) { Write-Host '  DeepMosaic API : http://127.0.0.1:8081/status' -ForegroundColor White }
Write-Host ''
Write-Host '  Logs: data\logs\*.log' -ForegroundColor DarkGray
Write-Host ''
Write-Host 'To stop everything:'
Write-Host '  powershell -ExecutionPolicy Bypass -File scripts\start-social-hunt.ps1 -Stop' -ForegroundColor Cyan
Write-Host ''
Write-Host 'TIP: Use 127.0.0.1 (not localhost) - uvicorn binds IPv4 0.0.0.0 and' -ForegroundColor DarkGray
Write-Host '     Windows often resolves localhost to IPv6 ::1, which is not served.' -ForegroundColor DarkGray
Write-Host ''
