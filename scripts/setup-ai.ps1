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

.PARAMETER GPU
  Install CUDA-enabled torch in .venv-iopaint so the SD demask worker uses
  the GPU (e.g. RTX 4090) instead of CPU. iopaint==1.6.0 pulls CPU torch by
  default; this upgrades it to the matching CUDA build from the PyTorch
  index. Without this, --device cuda is silently downgraded to CPU and SD
  inpainting takes ~13 min/image instead of ~30s on a 4090.

.EXAMPLE
  pwsh scripts/setup-ai.ps1
  pwsh scripts/setup-ai.ps1 -Force
  pwsh scripts/setup-ai.ps1 -GPU
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$GPU
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

    Write-Host '[2/5] Upgrading pip in .venv-iopaint ...'
    & $IopaintPy -m pip install --upgrade pip wheel | Out-Null

    Write-Host '[3/5] Installing iopaint==1.6.0 (this pulls torch 2.1.2 + Pillow 9.5.0, isolated here) ...'
    & $IopaintPy -m pip install 'iopaint==1.6.0'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[error] iopaint install failed. Network or wheel issue.' -ForegroundColor Red
        exit 1
    }

    # CUDA torch upgrade: iopaint==1.6.0 pulls CPU-only torch by default on
    # Windows. The SD demask worker (start-social-hunt.ps1 section 2b) passes
    # --device cuda, but without a CUDA build of torch it silently falls back
    # to CPU with just a warning, making SD inpainting take ~13 min/image on a
    # 4090. This step replaces the CPU wheel with the CUDA build from the
    # PyTorch index, keeping the same torch version (pip --force-reinstall
    # is needed because the version string is identical: 2.13.0 vs 2.13.0+cu).
    if ($GPU) {
        $torchVer = (& $IopaintPy -c 'import torch; print(torch.__version__)') 2>$null
        if ($torchVer -and ($torchVer -match '^(\d+\.\d+\.\d+)')) {
            $tv = $Matches[1]
            $tvMinor = $Matches[1].Split('.')[1]
            # torchvision version that ships with this torch (torch 2.x -> torchvision 0.(x+15).0)
            # but iopaint pins torchvision loosely; just reinstall the matching CUDA build.
            Write-Host "[3.5/5] Upgrading torch $tv to CUDA build (GPU mode) ..." -ForegroundColor Cyan
            # cu126 has torch 2.13.0; fall back to the index that carries this version.
            & $IopaintPy -m pip install --no-cache-dir --force-reinstall "torch==$tv" 'torchvision' --index-url https://download.pytorch.org/whl/cu126
            if ($LASTEXITCODE -ne 0) {
                Write-Host '[warn] CUDA torch install failed; SD worker will fall back to CPU.' -ForegroundColor Yellow
            } else {
                $cudaOk = (& $IopaintPy -c 'import torch; print(torch.cuda.is_available())') 2>$null
                if ($cudaOk -match 'True') {
                    $devName = (& $IopaintPy -c 'import torch; print(torch.cuda.get_device_name(0))') 2>$null
                    Write-Host "[info] CUDA torch OK: $devName" -ForegroundColor Green
                } else {
                    Write-Host '[warn] CUDA torch installed but torch.cuda.is_available() is False.' -ForegroundColor Yellow
                }
            }
        } else {
            Write-Host '[warn] Could not detect torch version; skipping CUDA upgrade.' -ForegroundColor Yellow
        }
    } else {
        Write-Host '[info] Skipping CUDA torch upgrade (no -GPU flag). SD demask will run on CPU.' -ForegroundColor DarkGray
    }

    # pillow-avif-plugin: Pillow 9.5.0 (pinned by iopaint 1.6.0) cannot decode
    # AVIF images. Browsers and phone cameras increasingly save .jpg files
    # that are actually AVIF (magic bytes 'ftypavif'); the WebUI canvas renders
    # them fine via native browser AVIF support, but the backend Image.open()
    # raises UnidentifiedImageError -> 500 'cannot identify image file'. The
    # plugin registers itself on PIL import, so it must be installed AFTER
    # iopaint (which pins Pillow).
    Write-Host '[4/5] Installing pillow-avif-plugin (adds AVIF decode to Pillow 9.5.0) ...'
    & $IopaintPy -m pip install 'pillow-avif-plugin'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[warn] pillow-avif-plugin install failed; AVIF .jpg uploads will fail.' -ForegroundColor Yellow
    } else {
        # pillow-avif-plugin requires an explicit 'import pillow_avif' to
        # register .avif/.avifs with PIL. IOPaint never imports it, so installing
        # the package alone is not enough. A .pth file with an 'import' line is
        # executed by site.py at every interpreter startup in this venv, so the
        # plugin auto-loads before IOPaint touches PIL. Without this, AVIF files
        # (commonly saved with a .jpg extension by phones/browsers) crash the
        # inpaint endpoint with 'cannot identify image file'.
        $PthPath = Join-Path $IopaintVenv 'Lib\site-packages\zz_pillow_avif.pth'
        Set-Content -Path $PthPath -Value 'import pillow_avif' -NoNewline -Encoding UTF8
        Write-Host '[info] wrote zz_pillow_avif.pth (auto-imports pillow_avif at startup)' -ForegroundColor DarkGray
    }

    Write-Host '[5/5] Verifying iopaint import ...'
    # Avoid double quotes in -c (PowerShell strips them for native commands).
    & $IopaintPy -c 'import iopaint'
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[warn] iopaint import check returned non-zero, but install reported success.' -ForegroundColor Yellow
    } else {
        Write-Host '[info] iopaint import OK'
    }

    # Patch iopaint/api.py: the WebUI frontend sometimes sends an empty or
    # corrupted multipart upload to /api/v1/gen-info (a browser bug in IOPaint
    # 1.6.0). load_img() then raises UnidentifiedImageError and the request
    # 500s, surfacing as "cannot identify image file <_io.BytesIO object>".
    # We replace the def+load_img block with a guarded version that returns
    # empty GenInfoResponse on empty/invalid data. Uses regex (not line
    # skipping) so the original load_img call can never survive the patch.
    # Re-applied after every install because the wheel is not editable in git.
    $IoApiPy = Join-Path $IopaintVenv 'Lib\site-packages\iopaint\api.py'
    if (Test-Path $IoApiPy) {
        $patchPy = @"
import sys, re
p = sys.argv[1]
with open(p, encoding='utf-8') as f:
    text = f.read()
if 'Guard against empty/corrupted multipart uploads' in text:
    # Idempotent: also strip a leftover duplicate original load_img line
    # from a previous buggy patch run, so re-running setup-ai.ps1 fixes it.
    text2 = re.sub(
        r'(return GenInfoResponse\(prompt="", negative_prompt=""\)\n)(\s*_, _, info = load_img\(file\.file\.read\(\), return_info=True\)\n)',
        r'\1',
        text,
        count=1
    )
    if text2 != text:
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text2)
        print('FIXED leftover duplicate load_img in api_geninfo')
    else:
        print('already patched')
    sys.exit(0)
pattern = r'def api_geninfo\(self, file: UploadFile\) -> GenInfoResponse:\n\s*_, _, info = load_img\(file\.file\.read\(\), return_info=True\)'
replacement = '''def api_geninfo(self, file: UploadFile) -> GenInfoResponse:
        # Guard against empty/corrupted multipart uploads from the WebUI
        # frontend (browser sends an empty file). Without this, load_img
        # raises UnidentifiedImageError and the request 500s.
        data = file.file.read()
        if not data:
            return GenInfoResponse(prompt="", negative_prompt="")
        try:
            _, _, info = load_img(data, return_info=True)
        except Exception:
            return GenInfoResponse(prompt="", negative_prompt="")'''
new_text = re.sub(pattern, replacement, text, count=1)
if new_text != text:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print('PATCHED api_geninfo')
else:
    print('api_geninfo pattern not found')
"@
        $patchScript = Join-Path $env:TEMP 'iopaint_geninfo_patch.py'
        Set-Content -Path $patchScript -Value $patchPy -Encoding UTF8
        & $IopaintPy $patchScript $IoApiPy 2>&1 | ForEach-Object { Write-Host "[info] iopaint patch: $_" -ForegroundColor DarkGray }
    }

    # Patch iopaint/helper.py: decode_base64_to_image crashes with
    # UnidentifiedImageError when the WebUI frontend sends empty/None base64
    # to /api/v1/inpaint (same browser bug as gen-info, but on the inpaint
    # endpoint), OR when the uploaded image is in a format Pillow cannot
    # decode (e.g. AVIF without pillow-avif-plugin). Add a guard that raises a
    # clear ValueError instead, including the first 16 bytes of the image so
    # the magic bytes (e.g. 'ftypavif') are visible in the 400 response.
    $IoHelperPy = Join-Path $IopaintVenv 'Lib\site-packages\iopaint\helper.py'
    if (Test-Path $IoHelperPy) {
        $helperPatch = @"
import sys, re
p = sys.argv[1]
with open(p, encoding='utf-8') as f:
    text = f.read()
if 'Guard: empty/None encoding from WebUI frontend' in text:
    print('already patched'); sys.exit(0)
pattern = r'def decode_base64_to_image\(\s*encoding: str, gray=False\s*\) -> Tuple\[np\.array, Optional\[np\.array\], Dict, str\]:.*?image = Image\.open\(io\.BytesIO\(image_bytes\)\)'
replacement = '''def decode_base64_to_image(
    encoding: str, gray=False
) -> Tuple[np.array, Optional[np.array], Dict, str]:
    # Guard: empty/None encoding from WebUI frontend (IOPaint 1.6.0 browser bug
    # sends empty base64 when the canvas image isn't loaded yet).
    if not encoding:
        raise ValueError("Empty image data received from frontend")
    if isinstance(encoding, str) and (encoding.startswith("data:image/") or encoding.startswith("data:application/octet-stream;base64,")):
        encoding = encoding.split(";")[1].split(",")[1]
    if not encoding:
        raise ValueError("Empty image data after stripping data URL prefix")
    try:
        image_bytes = base64.b64decode(encoding)
    except Exception:
        raise ValueError("Invalid base64 image data from frontend")
    if not image_bytes:
        raise ValueError("Decoded image bytes are empty")
    ext = get_image_ext(image_bytes)
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        first_bytes = image_bytes[:16].hex() if image_bytes else 'empty'
        raise ValueError(
            f"Cannot decode image (format unsupported by Pillow): {e}. "
            f"bytes_len={len(image_bytes)}, first_bytes_hex={first_bytes}"
        )'''
new_text = re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)
if new_text != text:
    with open(p, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print('PATCHED helper.py')
else:
    print('helper.py pattern not found')
"@
        $patchScript2 = Join-Path $env:TEMP 'iopaint_helper_patch.py'
        Set-Content -Path $patchScript2 -Value $helperPatch -Encoding UTF8
        & $IopaintPy $patchScript2 $IoHelperPy 2>&1 | ForEach-Object { Write-Host "[info] iopaint helper patch: $_" -ForegroundColor DarkGray }
    }

    # Patch iopaint/api.py api_inpaint: wrap decode_base64_to_image calls
    # in try/except so invalid data returns HTTP 400 instead of crashing 500.
    if (Test-Path $IoApiPy) {
        $inpaintPatch = @"
import sys
p = sys.argv[1]
with open(p, encoding='utf-8') as f:
    lines = f.readlines()
if any('Guard: empty image from frontend' in l for l in lines):
    print('already patched'); sys.exit(0)
out = []
patched = False
for i, line in enumerate(lines):
    if 'def api_inpaint(self, req: InpaintRequest):' in line and not patched:
        out.append(line)
        out.append('        # Guard: empty image from frontend (IOPaint 1.6.0 WebUI bug)\n')
        out.append('        try:\n')
        out.append('            image, alpha_channel, infos, ext = decode_base64_to_image(req.image)\n')
        out.append('            mask, _, _, _ = decode_base64_to_image(req.mask, gray=True)\n')
        out.append('        except ValueError as e:\n')
        out.append('            raise HTTPException(status_code=400, detail=str(e))\n')
        out.append('        except Exception as e:\n')
        out.append('            raise HTTPException(status_code=400, detail=f"Invalid image or mask data: {e}")\n')
        patched = True
        continue
    if not patched and 'image, alpha_channel, infos, ext = decode_base64_to_image(req.image)' in line:
        continue
    if not patched and 'mask, _, _, _ = decode_base64_to_image(req.mask, gray=True)' in line:
        continue
    out.append(line)
with open(p, 'w', encoding='utf-8') as f:
    f.writelines(out)
print('PATCHED api_inpaint' if patched else 'NOT FOUND')
"@
        $patchScript3 = Join-Path $env:TEMP 'iopaint_inpaint_patch.py'
        Set-Content -Path $patchScript3 -Value $inpaintPatch -Encoding UTF8
        & $IopaintPy $patchScript3 $IoApiPy 2>&1 | ForEach-Object { Write-Host "[info] iopaint inpaint patch: $_" -ForegroundColor DarkGray }
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

    Write-Host '[4/6] Installing DeepMosaic runtime deps (opencv, ffmpeg, fastapi, uvicorn, gdown) ...'
    & $DmPy -m pip install 'opencv-python-headless' 'ffmpeg-python' 'tqdm' 'pillow' 'numpy<2.0' 'fastapi' 'uvicorn[standard]' 'python-multipart' 'aiofiles' 'gdown'
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

    # Patch DeepMosaics to be non-interactive: the upstream code calls
    # input('Please press any key to exit.\n') on missing-model/wrong-mode
    # paths. Under the worker's stdin=DEVNULL this raises an uncaught EOFError
    # (exit code 1) instead of a clean error. Replace input() with print()+sys.exit(1).
    # DeepMosaics/ is .gitignore'd, so this patch must be re-applied after every
    # fresh clone — hence we run it unconditionally here.
    $OptPy = Join-Path $Root 'DeepMosaics\cores\options.py'
    $DmPy2  = Join-Path $Root 'DeepMosaics\deepmosaic.py'
    foreach ($f in @($OptPy, $DmPy2)) {
        if (Test-Path $f) {
            $txt = Get-Content $f -Raw
            $orig = $txt
            $txt = $txt -replace "input\('Please press any key to exit\.\\n'\)", 'sys.exit(1)'
            $txt = $txt -replace "input\('Please check mosaic_position_model_path!'\)", "print('Error: Please check mosaic_position_model_path!')"
            if ($txt -ne $orig) {
                Set-Content $f -Value $txt -NoNewline
                Write-Host "[info] Patched non-interactive exits in $f" -ForegroundColor DarkGray
            }
        }
    }

    # Patch DeepMosaics loadmodel.py: add strict=False to every load_state_dict
    # call. The upstream checkpoints (clean_face_HD.pth, mosaic_position.pth,
    # add_face.pth) were saved with older PyTorch and contain key mismatches
    # (extra/missing keys) under torch>=2.x. Without strict=False the loader
    # raises RuntimeError: Error(s) in loading state_dict for ... and the whole
    # /process job crashes with exit 1. The remote-mode worker (non-Docker
    # deploy) never runs apply_compat_patches() at runtime (it returns early
    # when self.remote is True), so this patch must be applied here, after the
    # clone, to survive a fresh setup. DeepMosaics/ is .gitignore'd.
    $LoadmodelPy = Join-Path $Root 'DeepMosaics\models\loadmodel.py'
    if (Test-Path $LoadmodelPy) {
        $txt = Get-Content $LoadmodelPy -Raw
        $orig = $txt
        # pix2pix / video netG loaders (opt.model_path)
        $txt = $txt -replace 'netG\.load_state_dict\(torch\.load\(opt\.model_path\)\)', 'netG.load_state_dict(torch.load(opt.model_path), strict=False)'
        # style netG loader (state_dict variable)
        $txt = $txt -replace 'netG\.load_state_dict\(state_dict\)', 'netG.load_state_dict(state_dict, strict=False)'
        # bisenet roi loader
        $txt = $txt -replace 'net\.load_state_dict\(torch\.load\(opt\.model_path\)\)', 'net.load_state_dict(torch.load(opt.model_path), strict=False)'
        # bisenet mosaic_position loader
        $txt = $txt -replace 'net\.load_state_dict\(torch\.load\(opt\.mosaic_position_model_path\)\)', 'net.load_state_dict(torch.load(opt.mosaic_position_model_path), strict=False)'
        if ($txt -ne $orig) {
            Set-Content $LoadmodelPy -Value $txt -NoNewline
            Write-Host '[info] Patched strict=False in loadmodel.py' -ForegroundColor DarkGray
        }
    }

    # Patch DeepMosaics cores/clean.py: guard against None from impro.imread.
    # cv2.imdecode returns None for corrupted/empty/unsupported uploads, and
    # the None propagates to get_mosaic_position as 'NoneType has no shape',
    # a cryptic error. Insert a clear RuntimeError right after imread.
    $CleanPy = Join-Path $Root 'DeepMosaics\cores\clean.py'
    if (Test-Path $CleanPy) {
        $cleanPatch = @"
import sys
p = sys.argv[1]
with open(p, encoding='utf-8') as f:
    lines = f.readlines()
if any('if img_origin is None:' in l for l in lines):
    print('already patched'); sys.exit(0)
out = []
patched = False
for line in lines:
    out.append(line)
    if 'img_origin = impro.imread(path)' in line and not patched:
        out.append('    if img_origin is None:\n')
        out.append('        raise RuntimeError(f\'Could not read image: {path}. The file may be corrupted or in an unsupported format.\')\n')
        patched = True
with open(p, 'w', encoding='utf-8') as f:
    f.writelines(out)
print('PATCHED' if patched else 'NOT FOUND')
"@
        $patchScript = Join-Path $env:TEMP 'deepmosaic_clean_patch.py'
        Set-Content -Path $patchScript -Value $cleanPatch -Encoding UTF8
        & $DmPy $patchScript $CleanPy 2>&1 | ForEach-Object { Write-Host "[info] clean.py patch: $_" -ForegroundColor DarkGray }
    }

    Write-Host '[6/6] Downloading DeepMosaic models (non-interactive) ...'
    # The downloader now supports --yes which auto-answers every prompt so it
    # runs cleanly with no stdin (it previously aborted on the first prompt).
    $DlScript = Join-Path $Root 'download_deepmosaic_models.py'
    if (Test-Path $DlScript) {
        & $DmPy $DlScript --yes 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[warn] download_deepmosaic_models.py exited non-zero. Models may be incomplete.' -ForegroundColor Yellow
        } else {
            Write-Host '[info] Model download step finished.' -ForegroundColor DarkGray
        }
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
Write-Host '  Social-Hunt      : http://127.0.0.1:8000'
Write-Host '  IOPaint WebUI    : http://127.0.0.1:8080'
Write-Host '  IOPaint SD demask: http://127.0.0.1:8082  (requires -GPU for CUDA)'
Write-Host '  DeepMosaic API   : http://127.0.0.1:8081/status'
Write-Host ''
Write-Host 'NOTE: If DeepMosaics models are missing, /process will return 500.'
Write-Host '      Re-run this script or manually run download_deepmosaic_models.py.' -ForegroundColor DarkGray
Write-Host 'NOTE: For GPU-accelerated SD demasking, re-run with -GPU to install CUDA torch.' -ForegroundColor DarkGray
Write-Host ''