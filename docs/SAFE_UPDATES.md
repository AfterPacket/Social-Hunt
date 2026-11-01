# Safe updates on a Raspberry Pi or development machine

## What Update System now does

The authenticated update endpoint fetches the current branch's configured remote and accepts only a fast-forward to its configured upstream. It does not change your remote or branch. A clean repository with no local-only commits can update without a manual merge/rebase, regardless of your `pull.rebase` preference.

The updater refuses to proceed if it finds:

- An unfinished merge/rebase/cherry-pick/revert/bisect, unresolved files, or a Git index lock.
- Modified tracked files, nonignored untracked files, dirty submodules, or index flags that might hide edits.
- A detached HEAD, missing upstream, or local-only/divergent commits.
- Incoming changes to tracked `data/` contents or `.env` that need a private configuration migration.

A repository-local update lock prevents concurrent button clicks and multiple app workers from running this updater simultaneously. It does not prevent someone from editing files or running Git manually, so avoid concurrent deployment changes. Checks run again after fetch. The updater never auto-stashes, commits, rebases, resets, cleans, or pushes. It does not automatically update submodules.

The old updater hid three paths using `assume-unchanged`. The new updater removes that flag from tracked `data/settings.json`, `docker/Dockerfile`, and `docker/docker-compose.yml` so real changes are visible and cannot be silently ignored. It will stop rather than discard those changes. `.gitignore` does not protect files that Git already tracks.

Requirements are installed with the running server's Python interpreter only when changed, or when a previous requirements installation is pending. A failed installation can be retried using Update System. Source updates are not rolled back automatically if package installation fails. Restart after a source update or dependency retry. No raw Git or pip output is returned to the browser: URLs and package-index diagnostics can contain credentials. Network failures, operation timeouts, and permissions failures produce sanitized messages.

This is a conservative in-place updater, not an atomic release/rollback system. For production use, consider separate release directories/containers with a health check and a shared external data directory.

## One-time reconciliation for the Pi's divergent `dev`

The Pi reported 22 local commits ending at `a9b7ae82e94de6650dddcd1891d7ac4f0be33ab2`, including published `main` changes, and two remote-only fixes. That exact public merge commit has been included in remote `dev`, preserving the scan fixes and patched dependency minimums. A clean Pi still at that commit can now fast-forward without rebasing, creating another merge, or discarding its history.

Do not use the old running updater during this recovery. The new updater takes effect only after the new code is installed and the server restarted.

1. Back up settings and runtime data outside the checkout. Keep the existing stash and backup branches local. Never upload them or push `--all`.
2. Run `git status`. If an operation is active, finish it or use its matching abort command. Do not run abort commands for unrelated operations.
3. On a clean `dev` checkout, with your local backup branch already created:

   ```bash
   git config --local pull.ff only
   git fetch origin
   git merge --ff-only origin/dev
   ```

   This preserves all 22 commits as ancestors of the updated deployment. If it refuses to fast-forward, stop and inspect `git status` and `git log --left-right --oneline HEAD...origin/dev`: the device has other local commits/changes or an unfinished operation. Do not use blanket `--ours`/`--theirs`, reset, or force-push.
4. If the merge succeeds, activate the app's Python 3.11 environment and run:

   ```bash
   python -m pip install --upgrade -r requirements.txt
   python -m pip check
   ```

5. Restart using your existing process manager/start command, then hard-refresh the browser. Check the Settings update description mentions fast-forward-only updates.
6. Leave the previous stash unapplied until its changes have been reviewed. Applying old tracked source changes wholesale will make the updater stop again. Move machine configuration to ignored overrides/external settings instead.

The reconciliation includes only the known public Pi merge commit; no stash, private settings, or local-only unpublished commits were uploaded. Future private source commits can still leave a deployment ahead of upstream; the updater intentionally blocks them. Keep deployment checkouts clean, retain development work on a separate local branch, and integrate only reviewed, nonprivate source changes into the remote deployment branch.

## Keep machine configuration out of tracked code

- Keep tokens and integration keys in private settings or environment variables; never commit them to repair a pull.
- The application supports `SOCIAL_HUNT_SETTINGS_PATH`. Set it to an absolute path outside the checkout in the actual server/service environment. Stop the app, copy existing settings privately to that location with owner-only permissions, configure the service, and restart. Merely exporting a variable in an interactive shell does not change an already-running systemd service or Docker container.
- `data/settings.json` is tracked in the current repository. Ignoring that path alone does not make edits safe to pull over. Review and preserve its contents privately before returning the tracked copy to its repository version or switching deployments; the updater will not perform this migration for you.
- Put Compose changes in ignored `docker/docker-compose.override.yml` (or a Compose override filename recognized by your Compose version). Inspect the combined configuration locally; `docker compose config` may display secrets, so do not paste its output publicly.
- Keep venvs, uploads, generated output, caches, and custom local files in ignored locations. Make intentional source changes on a development branch, review for secrets, and integrate them into the remote deployment branch before updating the Pi.

For manual routine updates on a clean deployment checkout, use `git pull --ff-only`. Do not set global autostash or make a blanket automatic-conflict resolver: it can silently restore obsolete code or expose private configuration in a commit.
