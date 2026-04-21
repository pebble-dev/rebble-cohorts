# rebble-cohorts
cohorts.rebble.io: The Rebble cohorts API. It handles firmware delivery.

For archival, use `/cohort?select=fw-all`, which returns a list of all stored firmware.

## Configuration

Environment variables:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | — | SQLAlchemy DB URL, e.g. `postgresql+psycopg://user:pw@host:5432/cohorts` |
| `FIRMWARE_ROOT` | no | `https://binaries.rebble.io/fw` | Base URL used by `import_json` and `fetch_firmware` to build `.pbz` URLs |
| `HONEYCOMB_KEY` | no | — | Honeycomb write key; beeline disabled if unset |
| `REBBLE_AUTH` | no | — | Rebble auth service URL; if unset, `Authorization` headers on `/cohort` are ignored |
| `MEMFAULT_TOKEN` | for `fetch_firmware` | — | Memfault project key |
| `AWS_ACCESS_KEY` / `AWS_SECRET_KEY` | for `fetch_firmware` | — | S3 creds for re-uploading firmware blobs |
| `S3_BUCKET` | for `fetch_firmware` | — | Target bucket (e.g. `rebble-binaries`) |
| `S3_PATH` | no | `fw/` | Key prefix inside `S3_BUCKET` (must align with the tail of `FIRMWARE_ROOT`) |
| `S3_ENDPOINT` | no | — | Custom S3 endpoint URL; leave unset for AWS |

## Local development

```
docker compose up --build                         # brings up postgres + app; auto-runs flask db upgrade
docker compose exec app uv run flask import_json  # one-shot seed from config.json (first run only)
```

The API is exposed on http://localhost:5000. Postgres data persists in the `cohorts-pg-data` named volume, run `docker compose down -v` if you want a fresh database.

## Firmware data

Firmware rows live in the `firmwares` table, keyed by `(hardware, kind, version)`. Multiple versions per `(hardware, kind)` are allowed so rollback works by submitting an older version with a newer timestamp — `/cohort?select=fw` always returns the latest row per requested kind by `timestamp` descending.

By default `/cohort?select=fw&hardware=<hw>` returns only `normal`. Pass `&includeRecovery=true` to additionally include the latest `recovery` row; only the literal string `true` is recognized, anything else (including absent) is treated as false. If none of the requested kinds yield a row, `/cohort` responds 400.

### Seeding from config.json

`config.json` is retained only as seed data for the initial import. After first boot, run:

```
docker compose exec app uv run flask import_json
```

Re-running is idempotent — rows are upserted by `(hardware, kind, version)`.

### Adding or updating a firmware

```
docker compose exec app uv run flask submit_firmware \
    <hardware> <kind> <version> <url> <sha256> \
    [--timestamp <unix>] [--notes "<text>"]
```

`kind` must be `normal` or `recovery`. `--timestamp` defaults to now. Re-running with the same `(hardware, kind, version)` upserts; submitting with a fresh timestamp is how you roll forward or back.

### Fetching CoreDevice firmware from Memfault

```
docker compose exec app uv run flask fetch_firmware
```

Checks Memfault's `releases/latest` for each CoreDevice hardware (asterix, obelix_*, getafix_*, obelix_bb*), skips versions already recorded, and for each new one: streams the `.pbz` down while hashing it, uploads it to S3 at `{S3_PATH}{hardware}/Pebble-{version}-{hardware}.pbz`, and upserts a `normal` row with the resulting `{FIRMWARE_ROOT}/…` URL and the computed sha256. Idempotent and safe to run from cron. Requires `MEMFAULT_TOKEN`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, and `S3_BUCKET` in the environment (docker-compose forwards these from the host). Supports `--token`.

### Migrations

`migrations/` is a standard Flask-Migrate / Alembic layout. `docker compose up` auto-applies pending migrations. To generate a new revision after editing models:

```
docker compose exec app uv run flask db migrate -m "<message>"
```

Commit the generated file under `migrations/versions/`. Migrations are authored against Postgres, so generating them via compose (which runs against the compose-managed Postgres) keeps the revisions dialect-accurate.
