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
docker compose up --build                         # brings up postgres + app; auto-runs flask db upgrade
docker compose exec app uv run flask import_json  # one-shot seed from config.json (first run only)
```

The API is exposed on http://localhost:5000. Postgres data persists in the `cohorts-pg-data` named volume, run `docker compose down -v` if you want a fresh database.

## Firmware data

Firmware rows live in the `firmwares` table, keyed by `(hardware, kind, version)`. `/cohort?select=fw&hardware=<hw>` returns the latest row per `kind` (`normal` / `recovery`) by `timestamp` descending. Multiple versions per `(hardware, kind)` are allowed so rollback works by submitting an older version with a newer timestamp.

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

### Migrations

`migrations/` is a standard Flask-Migrate / Alembic layout. `docker compose up` auto-applies pending migrations. To generate a new revision after editing models:

```
docker compose exec app uv run flask db migrate -m "<message>"
```

Commit the generated file under `migrations/versions/`. Migrations are authored against Postgres, so generating them via compose (which runs against the compose-managed Postgres) keeps the revisions dialect-accurate.
