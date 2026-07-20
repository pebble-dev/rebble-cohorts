import json
import time

import click
from flask import cli as flask_cli

from .memfault import fetch_firmware_command
from .models import Firmware, db
from .settings import config

VALID_FW_KINDS = ("normal", "recovery")


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
            raw_version = entry["version"]
            version = f"v{raw_version}"
            sha256 = entry["sha-256"]
            url = f"{config['FIRMWARE_ROOT']}/{hardware}/Pebble-{raw_version}-{hardware}.pbz"
            timestamp = timestamps_map[raw_version]
            notes = notes_map.get(raw_version)
            Firmware.upsert(hardware, kind, version, url, sha256, timestamp, notes)
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
    Firmware.upsert(hardware, kind, version, url, sha256, timestamp, notes)
    db.session.commit()
    click.echo(f"Submitted firmware {hardware}/{kind}/{version}.")


def init_app(app):
    app.cli.add_command(import_json_command)
    app.cli.add_command(submit_firmware_command)
    app.cli.add_command(fetch_firmware_command)
