import hashlib
import io
import time

import boto3
import click
import httpx
from flask import cli as flask_cli

from .models import Firmware, db
from .settings import config

MEMFAULT_API = "https://api.memfault.com/api/v0/releases/latest"

# Core Devices hardware revisions. These short names are both the `hardware`
# value we store in the firmwares table and the `hardware_version` string
# Memfault expects. Based on the mobileapp WatchHardwarePlatform.
CORE_DEVICES_DEVICES = (
    "asterix",
    "obelix_evt",
    "obelix_dvt",
    "obelix_pvt",
    "getafix_evt",
    "getafix_dvt",
    "obelix_bb",
    "obelix_bb2",
)


def _fetch_latest(client, token, hw_revision):
    resp = client.get(
        MEMFAULT_API,
        params={
            "hardware_version": hw_revision,
            "software_type": "pebbleos",
            "device_serial": "REBBLE_COHORTS_CRON",
        },
        headers={"Memfault-Project-Key": token},
    )
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


def _download_and_hash(client, url):
    sha256 = hashlib.sha256()
    buf = io.BytesIO()
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(chunk_size=8192):
            buf.write(chunk)
            sha256.update(chunk)
    buf.seek(0)
    return buf, sha256.hexdigest()


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=config["AWS_ACCESS_KEY"],
        aws_secret_access_key=config["AWS_SECRET_KEY"],
        endpoint_url=config["S3_ENDPOINT"],
    )


def _upload(data, s3_key):
    data.seek(0)
    _s3_client().upload_fileobj(
        data,
        config["S3_BUCKET"],
        s3_key,
        ExtraArgs={"ContentType": "application/octet-stream"},
    )


@click.command(name="fetch_firmware")
@click.option(
    "--token",
    default=None,
    help="Memfault project key (falls back to MEMFAULT_TOKEN env).",
)
@flask_cli.with_appcontext
def fetch_firmware_command(token):
    """Check Memfault for the latest firmware for each CoreDevice hardware,
    download + re-upload to our CDN, and upsert into the firmwares table."""
    token = token or config["MEMFAULT_TOKEN"]
    if not token:
        raise click.UsageError("MEMFAULT_TOKEN not set (pass --token or set the env var).")
    for var in ("AWS_ACCESS_KEY", "AWS_SECRET_KEY", "S3_BUCKET"):
        if not config[var]:
            raise click.UsageError(f"{var} env var not set.")

    added = 0
    skipped = 0
    failed = 0
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for hardware in CORE_DEVICES_DEVICES:
            click.echo(f"[{hardware}]: ", nl=False)
            try:
                info = _fetch_latest(client, token, hardware)
            except httpx.HTTPStatusError as e:
                click.echo(f"lookup FAILED ({e.response.status_code})")
                failed += 1
                continue

            if info is None:
                click.echo("no update available")
                continue

            version = info["version"]
            notes = info.get("notes") or None
            artifact_url = info["artifacts"][0]["url"]

            existing = Firmware.query.filter_by(
                hardware=hardware, kind="normal", version=version
            ).one_or_none()
            if existing is not None:
                click.echo(f"{version} already in DB, skipping")
                skipped += 1
                continue

            filename = f"Pebble-{version}-{hardware}.pbz"
            s3_key = f"{config['S3_PATH']}{hardware}/{filename}"
            public_url = f"{config['FIRMWARE_ROOT']}/{hardware}/{filename}"

            click.echo(f"{version} downloading... ", nl=False)
            try:
                data, sha256 = _download_and_hash(client, artifact_url)
            except httpx.HTTPStatusError as e:
                click.echo(f"download FAILED ({e.response.status_code})")
                failed += 1
                continue

            click.echo("uploading... ", nl=False)
            try:
                _upload(data, s3_key)
            except Exception as e:
                click.echo(f"upload FAILED ({e})")
                failed += 1
                continue

            Firmware.upsert(
                hardware=hardware,
                kind="normal",
                version=version,
                url=public_url,
                sha256=sha256,
                timestamp=int(time.time()),
                notes=notes,
            )
            db.session.commit()
            click.echo("OK")
            added += 1

    click.echo(f"done. {added} added, {skipped} already present, {failed} failed.")
