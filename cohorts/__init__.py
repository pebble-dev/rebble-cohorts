from functools import wraps
import logging
import os

logging.basicConfig(level=logging.INFO)

import beeline
from beeline.middleware.flask import HoneyMiddleware
from flask import Flask, jsonify, request, abort
from beeline.patch import requests
import requests

from . import firmware_fetcher

app = Flask(__name__)

app.config['HONEYCOMB_KEY'] = os.environ.get('HONEYCOMB_KEY', None)
app.config['REBBLE_AUTH'] = os.environ['REBBLE_AUTH']
app.config['FIRMWARE_ROOT'] = os.environ.get('FIRMWARE_ROOT', 'https://binaries.rebble.io/fw')

fw_config = firmware_fetcher.FirmwareConfig(app.config['FIRMWARE_ROOT'])
if os.environ.get('DISABLE_FIRMWARE_FETCHER') != '1':
    firmware_fetcher.start(fw_config)

if app.config['HONEYCOMB_KEY']:
    beeline.init(writekey=app.config['HONEYCOMB_KEY'], dataset='rws', service_name='cohorts')
    HoneyMiddleware(app)

def optional_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization')
        user = None
        if auth is not None:
            result = requests.get(f"{app.config['REBBLE_AUTH']}/api/v1/me", headers={'Authorization': auth})
            if result.status_code != 200:
                abort(401)
            user = result.json()
        return fn(user, *args, **kwargs)
    return wrapper


def build_fw_block(config, hw, kind):
    info = config['hardware'][hw][kind]
    version = info['version']
    return {
        'url': info['url'],
        'sha-256': info['sha-256'],
        'friendlyVersion': f"v{version}",
        'timestamp': config['timestamps'][version],
        'notes': config['notes'].get(version, f"v{version}")
    }


def generate_fw():
    # pull these all out for reference even though we don't use them all right now.
    hardware = request.args['hardware']
    mobile_platform = request.args['mobilePlatform']
    mobile_version = request.args['mobileVersion']
    mobile_hardware = request.args['mobileHardware']
    pebble_app_version = request.args['pebbleAppVersion']

    beeline.add_context_field('user.hardware', hardware)
    beeline.add_context_field('user.mobile_platform', mobile_platform)
    beeline.add_context_field('user.pebble_app_version', pebble_app_version)

    config = fw_config.get()
    if hardware not in config['hardware']:
        abort(400)
    fw = config['hardware'][hardware]
    response = {}
    if 'normal' in fw:
        response['normal'] = build_fw_block(config, hardware, 'normal')
    if 'recovery' in fw:
        response['recovery'] = build_fw_block(config, hardware, 'recovery')
    return response


generators = {
    'pipeline-api': lambda: {'host': 'pipeline-api.rebble.io'},
    'linked-services': lambda: {'enabled_providers': []},
    'health-insights': lambda: {
        'url': 'https://binaries.rebble.io/health-insights/v11/insights.pbhi',
        'version': 11,
    },
    'fw': generate_fw,
}


@app.route('/cohort')
@optional_auth
def cohort(user):
    if user and 'uid' in user:
        beeline.add_context_field('user', user['uid'])
    select = request.args['select'].split(',')
    response = {}
    for entry in select:
        if entry not in generators:
            abort(400)
        response[entry] = generators[entry]()
    return jsonify(response)

@app.route('/heartbeat')
@app.route('/cohorts/heartbeat')
def heartbeat():
    return 'ok'
