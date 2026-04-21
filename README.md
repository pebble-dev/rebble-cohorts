# rebble-cohorts
cohorts.rebble.io: The Rebble cohorts API

## Configuration

Environment variables:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | yes | — | SQLAlchemy DB URL, e.g. `postgresql+psycopg://user:pw@host:5432/cohorts` |
| `FIRMWARE_ROOT` | no | `https://binaries.rebble.io/fw` | Base URL used by `import_json` to build `.pbz` URLs |
| `HONEYCOMB_KEY` | no | — | Honeycomb write key; beeline disabled if unset |
| `REBBLE_AUTH` | no | — | Rebble auth service URL; if unset, `Authorization` headers on `/cohort` are ignored |

## Local development

```
docker run -d --name cohorts-pg \
    -e POSTGRES_USER=cohorts -e POSTGRES_PASSWORD=cohorts -e POSTGRES_DB=cohorts \
    -p 55432:5432 postgres:17-alpine

export DATABASE_URL='postgresql+psycopg://cohorts:cohorts@localhost:55432/cohorts'
export FLASK_APP=cohorts

uv sync
uv run flask db upgrade       # create tables
uv run flask import_json      # seed from config.json (one-shot)
uv run python serve_debug.py  # http://localhost:5000
```

## Firmware data

Firmware rows live in the `firmwares` table, keyed by `(hardware, kind, version)`. `/cohort?select=fw&hardware=<hw>` returns the latest row per `kind` (`normal` / `recovery`) by `timestamp` descending. Multiple versions per `(hardware, kind)` are allowed so rollback works by submitting an older version with a newer timestamp.

### Seeding from config.json

`config.json` is retained only as seed data for the initial import. After first boot, run:

```
uv run flask import_json
```

Re-running is idempotent — rows are upserted by `(hardware, kind, version)`.

### Adding or updating a firmware

```
uv run flask submit_firmware <hardware> <kind> <version> <url> <sha256> \
    [--timestamp <unix>] [--notes "<text>"]
```

`kind` must be `normal` or `recovery`. `--timestamp` defaults to now. Re-running with the same `(hardware, kind, version)` upserts; submitting with a fresh timestamp is how you roll forward or back.

### Migrations

`migrations/` is a standard Flask-Migrate / Alembic layout. After editing models:

```
uv run flask db migrate -m "<message>"
uv run flask db upgrade
```

Migrations are generated against Postgres; run the commands with a Postgres `DATABASE_URL` so the generated revision reflects the target dialect.
