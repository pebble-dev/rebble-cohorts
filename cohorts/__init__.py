import beeline
from beeline.middleware.flask import HoneyMiddleware
import beeline.propagation.w3c as w3c
from flask import Flask

import os

from .api import init_app as init_api
from .cli import init_app as init_cli
from .models import init_app as init_models
from .settings import config

app = Flask(__name__)
app.config.update(config)

if app.config["HONEYCOMB_KEY"]:
    if os.environ.get('O11Y_SHOULD_USE_W3C_TRACE_HEADERS', False):
        # Only turn this on once EVERYTHING has migrated to the new
        # rws_common version that supports W3C trace headers.
        beeline.init(writekey=app.config["HONEYCOMB_KEY"], dataset="rws", service_name="cohorts", http_trace_propagation_hook=w3c.http_trace_propagation_hook)
    else:
        beeline.init(writekey=app.config["HONEYCOMB_KEY"], dataset="rws", service_name="cohorts")
    HoneyMiddleware(app)

init_models(app)
init_api(app)
init_cli(app)
