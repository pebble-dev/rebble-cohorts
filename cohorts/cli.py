import json
import time

import click
from flask import cli as flask_cli

from .models import Firmware, db
from .settings import config

VALID_FW_KINDS = ("normal", "recovery")


def _upsert_firmware(hardware, kind, version, url, sha256, timestamp, notes):
    existing = Firmware.query.filter_by(hardware=hardware, kind=kind, version=version).one_or_none()
    if existing is None:
        db.session.add(
            Firmware(
                hardware=hardware,
                kind=kind,
                version=version,
                url=url,
                sha256=sha256,
                timestamp=timestamp,
                notes=notes,
            )
        )
    else:
        existing.url = url
        existing.sha256 = sha256
        existing.timestamp = timestamp
        existing.notes = notes


@click.command(name="import_json")
@flask_cli.with_appcontext
def import_json_command():
    with open("config.json") as f:
        fw_config = json.load(f)

    notes_map = fw_config.get("notes", {})
    timestamps_map = fw_config.get("timestamps", {})
    count = 0
    for hardware, variants in fw_config["hardware"].items():
        for kind, entry in variants.items():
            version = entry["version"]
            sha256 = entry["sha-256"]
            url = f"{config['FIRMWARE_ROOT']}/{hardware}/Pebble-{version}-{hardware}.pbz"
            timestamp = timestamps_map[version]
            notes = notes_map.get(version)
            _upsert_firmware(hardware, kind, version, url, sha256, timestamp, notes)
            count += 1
    db.session.commit()
    click.echo(f"Imported {count} firmware rows.")


@click.command(name="submit_firmware")
@click.argument("hardware")
@click.argument("kind")
@click.argument("version")
@click.argument("url")
@click.argument("sha256")
@click.option("--timestamp", type=int, default=None, help="Unix timestamp (default: now).")
@click.option("--notes", default=None, help="Release notes (optional).")
@flask_cli.with_appcontext
def submit_firmware_command(hardware, kind, version, url, sha256, timestamp, notes):
    if kind not in VALID_FW_KINDS:
        raise click.BadParameter(f"kind must be one of {VALID_FW_KINDS}, got {kind!r}")
    if timestamp is None:
        timestamp = int(time.time())
    _upsert_firmware(hardware, kind, version, url, sha256, timestamp, notes)
    db.session.commit()
    click.echo(f"Submitted firmware {hardware}/{kind}/{version}.")


def init_app(app):
    app.cli.add_command(import_json_command)
    app.cli.add_command(submit_firmware_command)
