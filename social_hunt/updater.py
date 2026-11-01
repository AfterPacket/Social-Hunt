"""Conservative server-side updates. Never merge, rebase, stash, reset, or push."""
from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
import subprocess
import sys


class UpdateStopped(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


def safe_update(root: Path, *, install_dependencies: bool = True) -> dict:
    root = Path(root).resolve()
    lock = None
    locked = False
    updated = False

    def git(*args, allowed=(0,)):
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True,
            timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if proc.returncode not in allowed:
            # Git output can contain credential-bearing URLs. Do not return it.
            raise UpdateStopped("git_failed", "Git could not complete the update. Check repository access locally; no automatic recovery was attempted.")
        return proc

    def git_path(name):
        path = Path(git("rev-parse", "--git-path", name).stdout.strip())
        return path if path.is_absolute() else root / path

    def preflight():
        if any(git_path(name).exists() for name in (
            "MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD",
            "REVERT_HEAD", "sequencer", "BISECT_START", "index.lock",
        )):
            raise UpdateStopped("operation_in_progress", "Update blocked: a merge, rebase, or other Git operation is unfinished. Run git status on the device and finish or abort that operation first.")
        if git("ls-files", "--unmerged").stdout:
            raise UpdateStopped("unmerged_files", "Update blocked: unresolved files exist. Run git status and resolve the existing conflict first; pulling again will not fix it.")
        # Undo only the flags set by the old Social-Hunt updater. These flags
        # hide edits; they are not a backup or configuration-preservation tool.
        for path in ("data/settings.json", "docker/Dockerfile", "docker/docker-compose.yml"):
            if git("ls-files", "--", path).stdout:
                git("update-index", "--no-assume-unchanged", "--", path)
        flags = git("ls-files", "-v").stdout.splitlines()
        if any(line and (line[0].islower() or line[0] == "S") for line in flags):
            raise UpdateStopped("hidden_edits", "Update blocked: Git index flags may hide local changes. Review assume-unchanged/skip-worktree entries locally before updating; sparse checkouts are not supported by this updater.")
        if git("status", "--porcelain", "--untracked-files=normal", "--ignore-submodules=none").stdout:
            raise UpdateStopped("local_changes", "Update blocked: local files or submodules have changes. Back them up and review them locally. Keep settings outside tracked files and use ignored Docker overrides. Nothing was stashed, committed, or discarded.")

    try:
        top = git("rev-parse", "--show-toplevel").stdout.strip()
        if Path(top).resolve() != root:
            raise UpdateStopped("not_checkout", "Update blocked: the application directory must be the root of a Git checkout. ZIP installations need a fresh clone.")
        lock = git_path("social-hunt-update.lock")
        try:
            lock.mkdir()
            locked = True
        except FileExistsError:
            raise UpdateStopped("update_busy", "Another update is running. If an earlier process crashed, verify no update is active before removing the .git/social-hunt-update.lock directory locally.")
        preflight()
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD", allowed=(0, 1))
        if branch.returncode:
            raise UpdateStopped("detached_head", "Update blocked: this checkout is not on a branch. Select the intended deployment branch locally first.")
        remote = git("config", "--get", f"branch.{branch.stdout.strip()}.remote", allowed=(0, 1)).stdout.strip()
        upstream = git("rev-parse", "--verify", "@{upstream}", allowed=(0, 128))
        if not remote or remote == "." or upstream.returncode:
            raise UpdateStopped("no_upstream", "Update blocked: this branch needs a configured remote upstream. Confirm the intended remote and branch locally first.")
        before = git("rev-parse", "HEAD").stdout.strip()
        req = root / "requirements.txt"
        before_requirements = req.read_bytes() if req.exists() else None
        git("fetch", "--no-recurse-submodules", "--", remote)
        target = git("rev-parse", "--verify", "@{upstream}^{commit}").stdout.strip()
        # Fetch may take time: check again before touching the work tree.
        preflight()
        if git("rev-parse", "HEAD").stdout.strip() != before:
            raise UpdateStopped("checkout_changed", "Update blocked: the checkout changed during the update. Retry after other Git activity has finished.")
        if git("merge-base", "--is-ancestor", before, target, allowed=(0, 1)).returncode:
            raise UpdateStopped("local_commits", "Update blocked: the branch has local-only or divergent commits. Review them locally and intentionally merge or rebase. The updater never rewrites history.")
        changed_paths = git("diff", "--name-only", "-z", before, target).stdout.split("\0")
        if any(p == ".env" or p.startswith("data/") for p in changed_paths if p):
            raise UpdateStopped("runtime_data_changed", "Update blocked: this update changes tracked runtime data or .env files. Back up private configuration outside the checkout and review this migration locally.")
        if target != before:
            # Explicit options override pull/merge preferences and avoid hooks.
            git("-c", "core.hooksPath=", "merge", "--ff-only", "--no-autostash", target)
            updated = True
        after_requirements = req.read_bytes() if req.exists() else None
        dependencies_changed = before_requirements != after_requirements
        # A marker allows a failed package install to be retried on the next
        # update even when Git is already current. No settings are stored here.
        pending = git_path("social-hunt-requirements-pending")
        if dependencies_changed:
            pending.touch()
        pip_ran = False
        if pending.exists() and install_dependencies:
            pip_ran = True
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                cwd=root, capture_output=True, text=True, timeout=900,
            )
            if proc.returncode:
                raise UpdateStopped("dependencies_failed", "Source is updated, but dependency installation failed. Check Python 3.11 and the virtual environment locally. Retry Update System to retry installation; do not downgrade security-fixed packages.")
            pending.unlink()
        return {
            "ok": True, "code": "updated" if updated else "up_to_date",
            "updated": updated, "restart_required": updated or pip_ran,
            "pip_ran": pip_ran, "pip_ok": not pending.exists(),
            "dependencies_changed": dependencies_changed,
            "message": ("Source updated safely. Restart the server to load the new code." if updated else "Dependencies installed. Restart the server." if pip_ran else "Already up to date.") + (" Dependencies still need installation." if pending.exists() else ""),
        }
    except UpdateStopped as exc:
        return {"ok": False, "code": exc.code, "message": exc.message,
                "updated": updated, "restart_required": updated}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "timeout", "updated": updated,
                "restart_required": updated,
                "message": "Update timed out. Check network/package installation locally before retrying. No raw command output is exposed because it may contain credentials."}
    except (OSError, ValueError):
        return {"ok": False, "code": "update_error", "updated": updated,
                "restart_required": updated,
                "message": "Update could not complete. Check Git installation and filesystem permissions locally."}
    finally:
        if locked:
            with suppress(OSError):
                lock.rmdir()
