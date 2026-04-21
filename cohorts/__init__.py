from functools import wraps
import json
import os

import beeline
from beeline.middleware.flask import HoneyMiddleware
from flask import Flask, jsonify, request, abort
from beeline.patch import requests

app = Flask(__name__)
with open("./config.json") as f:
    fw_config = json.load(f)

app.config["HONEYCOMB_KEY"] = os.environ.get("HONEYCOMB_KEY")
app.config["REBBLE_AUTH"] = os.environ.get("REBBLE_AUTH")
app.config["FIRMWARE_ROOT"] = os.environ.get("FIRMWARE_ROOT", "https://binaries.rebble.io/fw")

if app.config["HONEYCOMB_KEY"]:
    beeline.init(writekey=app.config["HONEYCOMB_KEY"], dataset="rws", service_name="cohorts")
    HoneyMiddleware(app)


def optional_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization")
        user = None
        rebble_auth_host = app.config["REBBLE_AUTH"]
        if auth and rebble_auth_host is not None:
            result = requests.get(f"{rebble_auth_host}/api/v1/me", headers={"Authorization": auth})
            if result.status_code != 200:
                abort(401)
            user = result.json()
        return fn(user, *args, **kwargs)

    return wrapper


def build_fw_block(hw, kind):
    info = fw_config["hardware"][hw][kind]
    version = info["version"]
    sha256 = info["sha-256"]
    timestamp = fw_config["timestamps"][version]
    return {
        "url": f"{app.config['FIRMWARE_ROOT']}/{hw}/Pebble-{version}-{hw}.pbz",
        "sha-256": sha256,
        "friendlyVersion": f"v{version}",
        "timestamp": timestamp,
        "notes": fw_config["notes"].get(version, f"v{version}"),
    }


def generate_fw():
    # pull these all out for reference even though we don't use them all right now.
    hardware = request.args["hardware"]
    mobile_platform = request.args["mobilePlatform"]
    mobile_version = request.args["mobileVersion"]  # noqa: F841
    mobile_hardware = request.args["mobileHardware"]  # noqa: F841
    pebble_app_version = request.args["pebbleAppVersion"]

    beeline.add_context_field("user.hardware", hardware)
    beeline.add_context_field("user.mobile_platform", mobile_platform)
    beeline.add_context_field("user.pebble_app_version", pebble_app_version)

    if hardware not in fw_config["hardware"]:
        abort(400)
    fw = fw_config["hardware"][hardware]
    response = {}
    if "normal" in fw:
        response["normal"] = build_fw_block(hardware, "normal")
    if "recovery" in fw:
        response["recovery"] = build_fw_block(hardware, "recovery")
    return response


generators = {
    "pipeline-api": lambda: {"host": "pipeline-api.rebble.io"},
    "linked-services": lambda: {"enabled_providers": []},
    "health-insights": lambda: {
        "url": "https://binaries.rebble.io/health-insights/v11/insights.pbhi",
        "version": 11,
    },
    "fw": generate_fw,
}


@app.route("/cohort")
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


@app.route("/heartbeat")
@app.route("/cohorts/heartbeat")
def heartbeat():
    return "ok"
