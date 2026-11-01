# Pillow / Gradio security update

## Security minimums

The reported Pillow advisories require **Pillow >=13.0.0**; Pillow 12.3.0 remains affected. Gradio's reported FileExplorer traversal issue requires **Gradio >=6.16.0**.

References checked for this update:

- https://github.com/advisories/GHSA-5x8w-8jj5-q52h (Pillow FlashPix)
- https://github.com/advisories/GHSA-w889-685w-c8fh (Pillow Ghostscript)
- https://github.com/advisories/GHSA-j36p-7w88-g82j (Gradio FileExplorer)
- https://api.github.com/advisories?ecosystem=pip&affects=Pillow&per_page=100

The main requirements and both Docker requirements copies now require Pillow >=13.0.0,<14.0.0. Active legacy Torch/IOPaint pins were removed from the main environment because IOPaint 1.6.0 requires vulnerable Pillow 9.5.0. IOPaint remains a separate optional Compose service, whose startup command upgrades Pillow, Gradio and the other AI dependencies after installing the legacy application.

Pillow 13 requires Python >=3.11. CI uses Python 3.11, matching Docker.

## Remaining IOPaint work

The reported `iopaint/requirements.txt` belongs to the IOPaint submodule, which was not initialized in this checkout. These parent-repository edits do not change that submodule's manifest or resolve alerts against it.

Initialize it with `git submodule update --init iopaint` in a Git checkout. Update its Pillow and Gradio requirements in a maintained upstream repository/fork, including packaging metadata and lock files. Test compatibility, commit there, then update the parent repository's submodule reference. Push and rescan the repository that owns the alerts. Do not merely dismiss them or create a requirements file in an uninitialized submodule.

IOPaint 1.6.0 declares obsolete exact pins. Installing newer dependencies afterwards may cause `pip check` conflicts and does not establish runtime compatibility. Use a tested maintained fork with corrected metadata. Keep the worker private pending import, CLI, upload, inpainting and UI tests. Do not downgrade back to vulnerable packages to satisfy the legacy metadata. Isolation alone is not a vulnerability fix.

## Apply to deployed environments

Source edits do not upgrade installed packages or running containers.

- Main app: in its Python 3.11 environment, run `python -m pip install --upgrade -r requirements.txt`, then restart it.
- Docker: rebuild the main image from this source; the Compose default prebuilt image will not automatically include these changes. Recreate IOPaint so its updated startup command executes, using the existing `iopaint` profile.
- In each relevant environment, check `python -m pip show Pillow gradio`, `python -m pip check`, and run `python -m pip_audit` after installing pip-audit. Gradio is needed only in the IOPaint environment.

Validation for this change covers offline scan classification and result rendering tests plus syntax checks. Full dependency installation, AI inference, browser/live-site checks, and production auditing were not performed. Do not mark all alerts resolved until the actual reported manifests and deployed environments have been updated and rescanned.
