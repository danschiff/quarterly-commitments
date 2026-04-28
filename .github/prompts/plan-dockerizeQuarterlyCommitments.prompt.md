# Plan: Dockerize Quarterly Commitments Tracker

Make Docker the only supported way to run the tracker. Add a `Dockerfile` (python:3.11-slim) and a `compose.yaml` with two services — `app` (runs `main.py`) and `test` (runs pytest) — that bind-mount the repo so generated artifacts land in the host working directory exactly as they do today. Secrets come from a gitignored `.env` file. Host venv instructions get removed from the README.

## Steps

### Phase 1 — Container image
1. Create `Dockerfile`:
   - Base `python:3.11-slim`.
   - Set `WORKDIR /app`, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`.
   - Copy `requirements.txt` first, `pip install --no-cache-dir -r requirements.txt` (better layer caching).
   - Copy the rest of the source.
   - Default `CMD ["python", "main.py"]`.
   - Run as a non-root user (create `app` user, `chown` `/app`) so bind-mounted files don't end up root-owned on Linux hosts.
2. Add `.dockerignore`: `.venv`, `__pycache__`, `*.pyc`, `.git`, `.pytest_cache`, `data-*.json`, `report-*.md`, `slack-drafts-*.md`, `reports/`, `_last_run.txt`, `.env`, `tests/_diag*`, `enhancements/`.

### Phase 2 — Compose orchestration
3. Create `compose.yaml` with two services sharing a YAML anchor for the common build/volume/env config:
   - `app`: default service. `command: python main.py`. Bind-mounts `.:/app`. Loads `.env` via `env_file`. Passes through `JIRA_API_TOKEN` (and future `SLACK_BOT_TOKEN`).
   - `test`: `command: python -m pytest tests/ -q`. Same bind mount; no secrets needed (uses mocked HTTP).
   - Both `tty: true`, `stdin_open: true` so console output renders cleanly.
4. Create `.env.example` documenting `JIRA_API_TOKEN=` (and `SLACK_BOT_TOKEN=` placeholder for future).
5. Add `.env` to `.gitignore` (verify `.gitignore` exists; create if missing).

### Phase 3 — Documentation
6. Rewrite README sections:
   - **Prerequisites**: Docker Desktop (or Docker Engine + compose plugin). Remove Python 3.11 / venv / pip lines.
   - **Getting started**: clone → `cp .env.example .env` → edit `.env` with token → edit `config.yaml` → `docker compose run --rm app`.
   - **Useful flags**: `docker compose run --rm app python main.py --refresh`, `... --data path/to/data.json`.
   - **Tests**: `docker compose run --rm test`.
   - Note that outputs land in the repo root / `reports/YYYY-MM-DD/` exactly as before because of the bind mount.
7. Update the "Keeping this README current" heuristic list if any items reference venv.

## Relevant files
- `Dockerfile` (new) — image definition.
- `compose.yaml` (new) — `app` + `test` services with bind mount and `env_file`.
- `.dockerignore` (new) — keep build context small and avoid copying generated artifacts/secrets into the image.
- `.env.example` (new) — documents required env vars.
- `.gitignore` — ensure `.env` is excluded (create file if it doesn't exist).
- `README.md` — replace Prerequisites/Getting started/Run/Tests sections with Docker-based instructions; remove venv references.
- `requirements.txt` — unchanged (already minimal: `requests`, `PyYAML`).
- `main.py`, `config.yaml`, `tests/` — unchanged.

## Verification
1. `docker compose build app` succeeds with no warnings about missing files.
2. `docker compose run --rm test` → pytest suite passes (same result as host run today).
3. `docker compose run --rm app` with a valid `.env` produces today's `data-YYYY-MM-DD.json`, `report-YYYY-MM-DD.md`, `slack-drafts-YYYY-MM-DD.md`, and `reports/YYYY-MM-DD/*.md` in the host repo (bind mount working).
4. Re-run `docker compose run --rm app` → uses the cached `data-*.json` (no Jira call), confirming the cache survives across container runs.
5. `docker compose run --rm app python main.py --refresh` re-fetches from Jira.
6. On Linux: confirm generated files are owned by the host user (non-root user in image, or matching UID), not root.
7. `git status` shows `.env` ignored; new top-level files (`Dockerfile`, `compose.yaml`, `.dockerignore`, `.env.example`) staged cleanly.

## Decisions
- Docker-only going forward; venv path removed from README (still works mechanically but unsupported).
- Bind-mount the repo working directory; no refactor of output paths.
- Two compose services (`app`, `test`); no scheduler.
- `python:3.11-slim` base, single-stage build (image size not a stated concern; keeps Dockerfile simple).
- `.env` file is the single secrets mechanism; host env vars are not a documented path.
- Out of scope: Slack bot integration (token slot reserved in `.env.example` only), CI workflow, image publishing to a registry, multi-arch builds.

## Further considerations
1. **Non-root UID matching on Linux.** Bind mounts + non-root container user can create file-ownership mismatches on Linux. Options: (A) leave container as root [simplest, but generated files owned by root on Linux]; (B) hardcode UID/GID 1000 [works for most devs]; (C) parameterize via build args `USER_UID`/`USER_GID` from `.env` [most flexible]. **Recommendation: B** — pragmatic default, easy to override later. Not a concern on Windows/macOS Docker Desktop.
2. **Pin Python patch version?** `python:3.11-slim` floats. Pinning (e.g. `python:3.11.9-slim-bookworm`) gives reproducible builds at the cost of needing periodic bumps. **Recommendation: pin** for the "reproducibility for teammates" goal you selected.
3. **Convenience wrapper.** A tiny `run.ps1` / `run.sh` that wraps `docker compose run --rm app "$@"` shortens the daily command back to `./run.ps1`. **Recommendation: skip for now**, add later if the compose command feels long.
