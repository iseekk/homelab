# Repository Instructions

## Project

Private home server on a Raspberry Pi (ARM64), run with Docker Compose:

- `tailscale` — VPN container; the only network entry point.
- `vaultwarden` — password manager, shares Tailscale's network stack (`network_mode: "service:tailscale"`), invisible on the LAN.
- `scheduler` — Python daemon in `scheduler/` that creates encrypted `.7z` backups of `vw-data/` and uploads them to local storage or S3.

This repository holds production secrets and password-vault backups. Treat every change as security-sensitive.

## Stack

- Docker Compose (ARM64)
- Python 3.14, managed with `uv`
- pydantic / pydantic-settings, boto3, py7zr, schedule
- pytest, pytest-cov, pytest-mock, freezegun
- Ruff (lint and format), mypy (`--strict`)
- GitHub Actions CI, pre-commit, Renovate (`renovate.json`)

## Structure

- `docker-compose.yml` — service definitions; images are pinned by tag and digest.
- `.env-example` — template for `.env` (`.env` is not tracked and contains real secrets).
- `scheduler/Dockerfile` — multi-stage image; runs as non-root user `1000`.
- `scheduler/src/scheduler/config.py` — `pydantic-settings` config read from environment variables.
- `scheduler/src/scheduler/main.py` — backend selection and the `schedule` loop.
- `scheduler/src/scheduler/backup/archiver.py` — collects Vaultwarden files and packages the archive.
- `scheduler/src/scheduler/backends/storage/` — `Storage` ABC with `local` and `s3` implementations.
- `scheduler/src/scheduler/backends/monitoring/` — `Monitor` ABC with `healthchecks` and `noop` implementations.
- `scheduler/tests/` — pytest suite, mirrors the `src` layout.

## Commands

Run from `scheduler/`:

- Install: `uv sync --frozen`
- Lint and format (auto-fix): `make lint`
- Type check: `make typecheck`
- Tests with coverage: `make test`
- Focused test: `uv run --frozen pytest tests/test_archiver.py -k "test_name"`

CI (`.github/workflows/ci.yml`) runs `ruff format --check`, `ruff check`, `mypy .` and `pytest`. Pre-commit runs lint and typecheck on commit and tests on push.

## Architecture

- Configuration lives in `Config`; runtime values come from environment variables (and optionally `.env` during local runs).
- `main.py` wires backends through `create_storage` and `create_monitor`; keep new backends behind the existing ABCs.
- `archiver.py` owns backup collection and compression; storage backends only receive finished archives.
- Do not query or modify Vaultwarden data outside the archiver's read-only access pattern.

## Conventions

- Full type annotations; `mypy --strict` must pass. Do not add `# type: ignore` without an error code and a reason.
- Ruff, line length 120, double quotes. Imports sorted, `pathlib` instead of `os.path`.
- Use `logging` with `%s` placeholders, not f-strings in log calls.
- New storage or monitoring backends implement the existing ABC and are wired in `create_storage` / `create_monitor` in `main.py`.
- Keep secrets in `SecretStr` and call `.get_secret_value()` only where the raw value is needed.
- Do not add a dependency without approval. Pin versions exactly (`==`) in `pyproject.toml` and update `uv.lock` with `uv lock`.

## Configuration Changes

A new environment variable must be added in all of these places:

1. A field in `Config` (`config.py`) with a default or validation.
2. `.env-example`, with a comment.
3. The service's `environment:` list in `docker-compose.yml`. Containers only receive the variables listed there.
4. `README.md`, if users need to know about it.
5. `tests/test_config.py`.

## Backup Invariants

Do not break these without explicit approval:

- Archives are always password-protected and header-encrypted; `ARCHIVE_PASSWORD` is required with at least 14 characters.
- SQLite is copied with the `sqlite3` backup API (hot backup), never by copying the file.
- The scheduler mounts `vw-data` read-only and must never write to it.
- Weekly and monthly copies are made only on the first scheduled run of the day.
- Local retention never deletes the newest file in a subdirectory.
- The S3 backend never deletes objects; retention is done by bucket lifecycle rules.
- A monitoring ping failure must not interrupt a backup.
- The container runs as non-root user `1000`.

## Testing

- Add or update tests for changed behavior, including failure cases.
- Mock `boto3`, HTTP calls and time (`pytest-mock`, `freezegun`); tests must not touch the network or real AWS.
- Use `tmp_path` for filesystem tests and synthetic data only.
- Do not weaken assertions to make a test pass.

## Docker and Dependencies

- Keep image tags pinned with `@sha256:` digests and GitHub Actions pinned by commit SHA. Renovate maintains them; do not unpin.
- Do not change `network_mode`, `cap_add`, `devices`, `user`, or volume mounts without approval; they define the isolation model.
- The target is ARM64. Do not introduce images or packages that lack ARM64 builds.

## Safety

- Never read, print, or commit `.env`, `ts-data/`, `vw-data/`, `backups/`, or any keys, tokens or passwords.
- Never log secrets or full config objects.
- Do not commit, push, run `docker compose` against the server, or run commands that delete data without approval.

## Completion

Before reporting done, run `make lint`, `make typecheck` and `make test` in `scheduler/`, and report:

- What changed and which files
- Commands run and their results
- Any check that was skipped, and remaining risks
