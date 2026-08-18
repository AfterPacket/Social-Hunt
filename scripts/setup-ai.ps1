<#
.SYNOPSIS
  One-time setup for the isolated AI worker venvs used by Social-Hunt on Windows
  (no Docker). Creates two separate Python environments so the vulnerable/heavy
  torch + Pillow 9.5.0 stack never touches the main Social-Hunt .venv (which
  stays on secure Pillow 12).

  - .venv-iopaint      -> runs IOPaint 1.6.0 (pins Pillow==9.5.0, torch==2.1.2) on :8080
  - .venv-deepmosaic   -> runs DeepMosaic worker (torch 2.1.2 + DeepMosaics) on :8081

.DESCRIPTION
  Run from any directory; resolves paths via $PSScriptRoot so the space + parens
  in the project path are handled correctly. Idempotent: re-running skips venvs
  that already exist unless you pass -Force.

.PARAMETER Force
  Recreate the AI venvs even if they already exist.

.EXAMPLE
  pwsh scripts/setup-ai.ps1
  pwsh scripts/setup-ai.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# Project root = parent of the scripts/ directory. Using $PSScriptRoot keeps us
# robust to the space + parens in "Social-Hunt-main (1)".
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

Write-Host ''
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host '      Social-Hunt AI worker setup (no Docker)'      -ForegroundColor Cyan
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host "Project root: $Root"
Write-Host ''

# --- Locate a suitable Python (3.11 preferred) --------------------------------
$Py = $null

# Prefer the project's main venv python if it exists (we know that's 3.11.9).
$MainVenvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $MainVenvPy) {
    $Py = $MainVenvPy
    Write-Host "[info] Using project venv Python: $Py"
} else {
    # Fall back to py launcher
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $candidate = & py -3.11 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate) {
            $Py = $candidate
            Write-Host "[info] Using py -3.11: $Py"
        }
    }
    if (-not $Py) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd) {
            $Py = & python -c 'import sys; print(sys.executable)'
            $ver = & $Py -c 'import sys; print(sys.version_info[:2])'
            Write-Host "[info] Using python: $Py (version $ver)"
        }
    }
}

if (-not $Py -or -not (Test-Path $Py)) {
    Write-Host '[error] No suitable Python found. Create .venv first with:' -ForegroundColor Red
    Write-Host '        py -3.11 -m venv .venv' -ForegroundColor Yellow
    exit 1
}

# Sanity: refuse Python 3.14+ (no wheels for numpy<2 / old torch).
# Use --version (not -c with f-strings) to avoid PowerShell double-quote stripping.
$verRaw = (& $Py --version 2>&1) | Out-String   # e.g. "Python 3.11.9\r\n"
$verMatch = [regex]::Match($verRaw, '(\d+)\.(\d+)')
if (-not $verMatch.Success) {
    Write-Host '[error] Could not determine Python version from --version output:' -ForegroundColor Red
    Write-Host "        $verRaw"
    exit 1
}
$verMajor = [int]$verMatch.Groups[1].Value
$verMinor = [int]$verMatch.Groups[2].Value
$verTuple = "$verMajor.$verMinor"
if ($verMajor -ge 3 -and $verMinor -ge 14) {
    Write-Host "[error] Python $verTuple is too new for the AI workers (need <=3.12). Install Python 3.11." -ForegroundColor Red
    exit 1
}
Write-Host "[info] Python version: $verTuple"
Write-Host ''

# -----------------------------------------------------------------------------
# 1) IOPaint venv (.venv-iopaint) -> :8080
# -----------------------------------------------------------------------------
$IopaintVenv = Join-Path $Root '.venv-iopaint'
$IopaintPy   = Join-Path $IopaintVenv 'Scripts\python.exe'

if ((Test-Path $IopaintPy) -and -not $Force) {
    Write-Host '[skip] .venv-iopaint already exists (use -Force to recreate)' -ForegroundColor DarkGray
} else {
    if ($Force -and (Test-Path $IopaintVenv)) {
        Write-Host '[clean] Removing old .venv-iopaint'
        Remove-Item -Recurse -Force $IopaintVenv
    }
    Write-Host '[1/4] Creating .venv-iopaint ...'
    & $Py -m venv $IopaintVenv
    if ($LASTEXITCODE -ne 0) { Write-Host '[error] venv creation failed' -ForegroundColor Red; exit 1 }

    Write-Host '[2/4] Upgrading pip in .venv-iopaint ...'
    & $IopaintPy -m pip install --upgrade pip wheel | Out-Null

    Write-Host '[3/4] Installing iopaint==1.6.0 (this pulls torch 2.1.2 + Pillow 9.5.0, isolated here) ...'
    & $IopaintPy -m pip install 'iopaint==1.6.0'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[error] iopaint install failed. Network or wheel issue.' -ForegroundColor Red
        exit 1
    }

    Write-Host '[4/4] Verifying iopaint import ...'
    # Avoid double quotes in -c (PowerShell strips them for native commands).
    & $IopaintPy -c 'import iopaint'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[warn] iopaint import check returned non-zero, but install reported success.' -ForegroundColor Yellow
    } else {
        Write-Host '[info] iopaint import OK'
    }
}
Write-Host ''

# -----------------------------------------------------------------------------
# 2) DeepMosaic venv (.venv-deepmosaic) -> :8081
# -----------------------------------------------------------------------------
$DmVenv = Join-Path $Root '.venv-deepmosaic'
$DmPy   = Join-Path $DmVenv 'Scripts\python.exe'

if ((Test-Path $DmPy) -and -not $Force) {
    Write-Host '[skip] .venv-deepmosaic already exists (use -Force to recreate)' -ForegroundColor DarkGray
} else {
    if ($Force -and (Test-Path $DmVenv)) {
        Write-Host '[clean] Removing old .venv-deepmosaic'
        Remove-Item -Recurse -Force $DmVenv
    }
    Write-Host '[1/6] Creating .venv-deepmosaic ...'
    & $Py -m venv $DmVenv
    if ($LASTEXITCODE -ne 0) { Write-Host '[error] venv creation failed' -ForegroundColor Red; exit 1 }

    Write-Host '[2/6] Upgrading pip in .venv-deepmosaic ...'
    & $DmPy -m pip install --upgrade pip wheel | Out-Null

    Write-Host '[3/6] Installing torch 2.1.2 (CPU) + torchvision 0.16.2 ...'
    & $DmPy -m pip install --extra-index-url https://download.pytorch.org/whl/cpu 'torch==2.1.2' 'torchvision==0.16.2'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[error] torch install failed.' -ForegroundColor Red
        exit 1
    }

    Write-Host '[4/6] Installing DeepMosaic runtime deps (opencv, ffmpeg, fastapi, uvicorn) ...'
    & $DmPy -m pip install 'opencv-python-headless' 'ffmpeg-python' 'tqdm' 'pillow' 'numpy<2.0' 'fastapi' 'uvicorn[standard]' 'python-multipart' 'aiofiles'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[error] DeepMosaic deps install failed.' -ForegroundColor Red
        exit 1
    }

    Write-Host '[5/6] Initializing DeepMosaics ...'
    # The project may have been downloaded as a ZIP (no .git), so submodule
    # init won't work. Clone directly if deepmosaic.py is missing.
    $DmSubmodule = Join-Path $Root 'DeepMosaics\deepmosaic.py'
    if (Test-Path $DmSubmodule) {
        Write-Host '[skip] DeepMosaics/deepmosaic.py already present.' -ForegroundColor DarkGray
    } else {
        $DmDir = Join-Path $Root 'DeepMosaics'
        if (Test-Path (Join-Path $Root '.git')) {
            # Proper git clone with submodules
            Push-Location $Root
            & git submodule update --init DeepMosaics
            Pop-Location
        } else {
            # No git repo (ZIP download) - clone directly
            Write-Host '[info] No .git found, cloning DeepMosaics directly ...'
            if (Test-Path $DmDir) { Remove-Item -Recurse -Force $DmDir }
            & git clone https://github.com/HypoX64/DeepMosaics.git $DmDir
        }
        if (-not (Test-Path $DmSubmodule)) {
            Write-Host '[warn] DeepMosaics/deepmosaic.py still missing. The worker will start but /process will fail.' -ForegroundColor Yellow
            Write-Host '       Try: git clone https://github.com/HypoX64/DeepMosaics.git DeepMosaics' -ForegroundColor Yellow
        }
    }

    Write-Host '[6/6] Downloading DeepMosaic models (non-interactive) ...'
    # The downloader prompts several times; we answer 'n' to everything so it
    # downloads what's missing and skips RAR re-extraction prompts. If the
    # models are already present it's a no-op.
    $DlScript = Join-Path $Root 'download_deepmosaic_models.py'
    if (Test-Path $DlScript) {
        # Pipe a stream of 'n' answers (one per prompt). Enough for all prompts.
        $answers = ('n','n','n','n','n','n','n','n','n','n') -join "`n"
        $answers | & $DmPy $DlScript 2>&1 | Out-Host
        Write-Host '[info] Model download step finished (see output above).'
    } else {
        Write-Host '[warn] download_deepmosaic_models.py not found; skipping model download.' -ForegroundColor Yellow
    }
}
Write-Host ''

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
Write-Host '==================================================' -ForegroundColor Green
Write-Host ' AI worker setup complete' -ForegroundColor Green
Write-Host '==================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Next step: start everything with'
Write-Host '  pwsh scripts/start-social-hunt.ps1' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Services (when started):'
Write-Host '  Social-Hunt   : http://127.0.0.1:8000'
Write-Host '  IOPaint WebUI : http://127.0.0.1:8080'
Write-Host '  DeepMosaic API: http://127.0.0.1:8081/status'
Write-Host ''
Write-Host 'NOTE: If DeepMosaics models are missing, /process will return 500.'
Write-Host '      Re-run this script or manually run download_deepmosaic_models.py.' -ForegroundColor DarkGray
Write-Host ''