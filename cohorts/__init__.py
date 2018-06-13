from functools import wraps
import json

from flask import Flask, jsonify, request, abort
import requests

app = Flask(__name__)
with open('./config.json') as f:
    fw_config = json.load(f)


# TODO: these should actually be configurable.
app.config['REBBLE_AUTH'] = 'https://auth.rebble.io'
app.config['FIRMWARE_ROOT'] = 'https://binaries.rebble.io/fw'


# TODO: Something like this probably belongs in a common library
def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization')
        if auth is None:
            abort(401)
        result = requests.get(f"{app.config['REBBLE_AUTH']}/api/v1/me", headers={'Authorization': auth})
        if result.status_code != 200:
            abort(401)
        return fn(*args, **kwargs)
    return wrapper


def build_fw_block(hw, kind):
    info = fw_config['hardware'][hw][kind]
    version = info['version']
    sha256 = info['sha-256']
    timestamp = fw_config['timestamps'][version]
    return {
        'url': f"{app.config['FIRMWARE_ROOT']}/{hw}/Pebble-{version}-{hw}.pbz",
        'sha-256': sha256,
        'friendlyVersion': f"v{version}",
        'timestamp': timestamp,
        'notes': fw_config['notes'].get(version, f"v{version}")
    }


def generate_fw():
    # pull these all out for reference even though we don't use them all right now.
    hardware = request.args['hardware']
    mobile_platform = request.args['mobilePlatform']
    mobile_version = request.args['mobileVersion']
    mobile_hardware = request.args['mobileHardware']
    pebble_app_version = request.args['pebbleAppVersion']
    if hardware not in fw_config['hardware']:
        abort(400)
    fw = fw_config['hardware'][hardware]
    response = {}
    if 'normal' in fw:
        response['normal'] = build_fw_block(hardware, 'normal')
    if 'recovery' in fw:
        response['recovery'] = build_fw_block(hardware, 'recovery')
    return response


generators = {
    'pipeline-api': lambda: {'host': 'pipeline-api.rebble.io'},
    'linked-services': lambda: {'enabled_providers': []},
    'fw': generate_fw,
}


@app.route('/cohort')
@require_auth
def cohort():
    select = request.args['select'].split(',')
    response = {}
    for entry in select:
        if entry not in generators:
            abort(400)
        response[entry] = generators[entry]()
    return jsonify(response)
