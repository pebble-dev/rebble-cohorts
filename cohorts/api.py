import json
import time
from functools import wraps

import beeline
import click
from beeline.patch import requests
from flask import Blueprint, abort, current_app, jsonify, request
from flask import cli as flask_cli

from .models import Firmware, db
from .settings import config

api = Blueprint("api", __name__)

VALID_FW_KINDS = ("normal", "recovery")


def optional_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        user = None
        rebble_auth_host = current_app.config["REBBLE_AUTH"]
        if auth and rebble_auth_host is not None:
            result = requests.get(f"{rebble_auth_host}/api/v1/me", headers={"Authorization": auth})
            if result.status_code != 200:
                abort(401)
            user = result.json()
        return fn(user, *args, **kwargs)

    return wrapper


def _latest_firmware(hardware, kind):
    return (
        Firmware.query.filter_by(hardware=hardware, kind=kind)
        .order_by(Firmware.timestamp.desc())
        .first()
    )


def generate_fw(kinds=("normal",)):
    # pull these all out for reference even though we don't use them all right now.
    hardware = request.args["hardware"]
    mobile_platform = request.args["mobilePlatform"]
    mobile_version = request.args["mobileVersion"]
    mobile_hardware = request.args["mobileHardware"]
    pebble_app_version = request.args["pebbleAppVersion"]

    beeline.add_context_field("user.hardware", hardware)
    beeline.add_context_field("user.mobile_platform", mobile_platform)
    beeline.add_context_field("user.pebble_app_version", pebble_app_version)

    response = {}
    for kind in kinds:
        row = _latest_firmware(hardware, kind)
        if row is not None:
            response[kind] = row.to_json()
    if not response:
        abort(400)
    return response


def _fw_generator():
    include_recovery = request.args.get("includeRecovery") == "true"
    kinds = ("normal", "recovery") if include_recovery else ("normal",)
    return generate_fw(kinds=kinds)


generators = {
    "pipeline-api": lambda: {"host": "pipeline-api.rebble.io"},
    "linked-services": lambda: {"enabled_providers": []},
    "health-insights": lambda: {
        "url": "https://binaries.rebble.io/health-insights/v11/insights.pbhi",
        "version": 11,
    },
    "fw": _fw_generator,
}


@api.route("/cohort")
@optional_auth
def cohort(user):
    if user and "uid" in user:
        beeline.add_context_field("user", user["uid"])
    select = request.args["select"].split(",")
    response = {}
    for entry in select:
        if entry not in generators:
            abort(400)
        response[entry] = generators[entry]()
    return jsonify(response)


@api.route("/heartbeat")
@api.route("/cohorts/heartbeat")
def heartbeat():
    return "ok"


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
    app.register_blueprint(api)
    app.cli.add_command(import_json_command)
    app.cli.add_command(submit_firmware_command)
