import os

config = {
    "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
    "HONEYCOMB_KEY": os.environ.get("HONEYCOMB_KEY"),
    "REBBLE_AUTH": os.environ.get("REBBLE_AUTH"),
    "FIRMWARE_ROOT": os.environ.get("FIRMWARE_ROOT", "https://binaries.rebble.io/fw"),
}
