"""Updater integration tests use only disposable local Git repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from social_hunt.updater import safe_update


@unittest.skipUnless(shutil.which("git"), "Git is required")
class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.origin = self.base / "origin.git"
        self.seed = self.base / "seed"
        self.app = self.base / "app"
        self.env = {**os.environ, "GIT_AUTHOR_NAME": "Test",
                    "GIT_AUTHOR_EMAIL": "test@example.invalid",
                    "GIT_COMMITTER_NAME": "Test",
                    "GIT_COMMITTER_EMAIL": "test@example.invalid"}
        self.git(self.base, "init", "--bare", "--initial-branch=dev", str(self.origin))
        self.git(self.base, "clone", str(self.origin), str(self.seed))
        self.commit(self.seed, "app.txt", "original\n")
        self.git(self.seed, "push", "-u", "origin", "dev")
        self.git(self.base, "clone", str(self.origin), str(self.app))

    def git(self, cwd, *args, allowed=(0,)):
        proc = subprocess.run(["git", *args], cwd=cwd, env=self.env,
                              capture_output=True, text=True)
        self.assertIn(proc.returncode, allowed, proc.stderr)
        return proc.stdout.strip()

    def commit(self, repo, name, text):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.git(repo, "add", "--", name)
        self.git(repo, "commit", "-m", "Test change")

    def publish(self, name="app.txt", text="remote\n"):
        self.commit(self.seed, name, text)
        self.git(self.seed, "push")

    def update(self):
        return safe_update(self.app, install_dependencies=False)

    def test_clean_fast_forward_and_already_current(self):
        self.publish()
        result = self.update()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["restart_required"])
        self.assertEqual((self.app / "app.txt").read_text(), "remote\n")
        self.assertEqual(self.update()["code"], "up_to_date")
        self.assertFalse((self.app / ".git/MERGE_HEAD").exists())

    def test_dirty_file_preserved(self):
        (self.app / "app.txt").write_text("local\n")
        self.publish()
        self.assertEqual(self.update()["code"], "local_changes")
        self.assertEqual((self.app / "app.txt").read_text(), "local\n")

    def test_divergence_never_creates_merge_conflict(self):
        self.commit(self.app, "app.txt", "local commit\n")
        before = self.git(self.app, "rev-parse", "HEAD")
        self.publish()
        self.assertEqual(self.update()["code"], "local_commits")
        self.assertEqual(self.git(self.app, "rev-parse", "HEAD"), before)
        self.assertFalse((self.app / ".git/MERGE_HEAD").exists())
        self.assertEqual(self.git(self.app, "ls-files", "-u"), "")

    def test_local_only_commit_is_not_silently_kept(self):
        self.commit(self.app, "local.txt", "keep\n")
        self.assertEqual(self.update()["code"], "local_commits")

    def test_existing_merge_conflict_is_untouched(self):
        self.commit(self.app, "app.txt", "local commit\n")
        self.publish()
        self.git(self.app, "fetch", "origin")
        self.git(self.app, "merge", "origin/dev", allowed=(1,))
        before = (self.app / "app.txt").read_bytes()
        self.assertEqual(self.update()["code"], "operation_in_progress")
        self.assertEqual((self.app / "app.txt").read_bytes(), before)

    def test_in_progress_rebase_and_update_lock(self):
        marker = self.app / ".git/rebase-merge"
        marker.mkdir()
        self.assertEqual(self.update()["code"], "operation_in_progress")
        marker.rmdir()
        lock = self.app / ".git/social-hunt-update.lock"
        lock.mkdir()
        self.assertEqual(self.update()["code"], "update_busy")
        self.assertTrue(lock.exists())

    def test_hidden_docker_edits_from_old_updater_are_detected(self):
        self.publish("docker/docker-compose.yml", "services: {}\n")
        self.assertTrue(self.update()["ok"])
        self.git(self.app, "update-index", "--assume-unchanged", "docker/docker-compose.yml")
        (self.app / "docker/docker-compose.yml").write_text("private local config\n")
        self.assertEqual(self.update()["code"], "local_changes")
        self.assertEqual((self.app / "docker/docker-compose.yml").read_text(), "private local config\n")

    def test_ignored_private_settings_are_untouched(self):
        self.publish(".gitignore", "data/\n.env\n")
        self.assertTrue(self.update()["ok"])
        private = self.app / "data/settings.json"
        private.parent.mkdir()
        private.write_text('{"example": "private fixture"}')
        self.publish()
        result = self.update()
        self.assertTrue(result["ok"], result)
        self.assertEqual(private.read_text(), '{"example": "private fixture"}')
        self.assertNotIn("private fixture", str(result))

    def test_remote_runtime_data_change_requires_review(self):
        self.publish("data/settings.json", "{}\n")
        before = self.git(self.app, "rev-parse", "HEAD")
        self.assertEqual(self.update()["code"], "runtime_data_changed")
        self.assertEqual(self.git(self.app, "rev-parse", "HEAD"), before)

    def test_detached_head(self):
        self.git(self.app, "checkout", "--detach")
        self.assertEqual(self.update()["code"], "detached_head")

    def test_no_upstream(self):
        self.git(self.app, "branch", "--unset-upstream")
        self.assertEqual(self.update()["code"], "no_upstream")

    def test_failure_does_not_return_git_credentials(self):
        sentinel = "private-output-must-not-escape"
        with patch("social_hunt.updater.subprocess.run", return_value=subprocess.CompletedProcess([], 128, "", sentinel)):
            result = self.update()
        self.assertFalse(result["ok"])
        self.assertNotIn(sentinel, str(result))

    def test_pending_install_can_retry_without_another_source_change(self):
        self.publish("requirements.txt", "# empty test requirements\n")
        self.assertTrue(self.update()["ok"])
        pending = self.app / ".git/social-hunt-requirements-pending"
        self.assertTrue(pending.exists())
        real_run = subprocess.run

        def run(args, **kwargs):
            if "pip" in args:
                return subprocess.CompletedProcess(args, 0, "", "")
            return real_run(args, **kwargs)

        with patch("social_hunt.updater.subprocess.run", side_effect=run):
            result = safe_update(self.app)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["pip_ran"])
        self.assertFalse(pending.exists())


if __name__ == "__main__":
    unittest.main()
