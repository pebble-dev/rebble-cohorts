from functools import wraps

import beeline
from beeline.patch import requests
from flask import Blueprint, abort, current_app, jsonify, request

from .models import Firmware

api = Blueprint("api", __name__)


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


FW_BEELINE_FIELDS = {
    "mobilePlatform": "user.mobile_platform",
    "mobileVersion": "user.mobile_version",
    "mobileHardware": "user.mobile_hardware",
    "pebbleAppVersion": "user.pebble_app_version",
}


def generate_fw(kinds=("normal",)):
    hardware = request.args["hardware"]
    beeline.add_context_field("user.hardware", hardware)
    for arg_name, field_name in FW_BEELINE_FIELDS.items():
        value = request.args.get(arg_name)
        if value is not None:
            beeline.add_context_field(field_name, value)

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


def init_app(app):
    app.register_blueprint(api)
