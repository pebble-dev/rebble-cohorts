import beeline
from beeline.middleware.flask import HoneyMiddleware
from flask import Flask

from .api import init_app as init_api
from .models import init_app as init_models
from .settings import config

app = Flask(__name__)
app.config.update(config)

if app.config["HONEYCOMB_KEY"]:
    beeline.init(writekey=app.config["HONEYCOMB_KEY"], dataset="rws", service_name="cohorts")
    HoneyMiddleware(app)

init_models(app)
init_api(app)
