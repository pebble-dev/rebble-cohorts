from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()


class Firmware(db.Model):
    __tablename__ = "firmwares"

    hardware = db.Column(db.String, primary_key=True, nullable=False)
    kind = db.Column(db.String, primary_key=True, nullable=False)
    version = db.Column(db.String, primary_key=True, nullable=False)
    url = db.Column(db.String, nullable=False)
    sha256 = db.Column(db.String, nullable=False)
    timestamp = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    def to_json(self, archival: bool = False):
        result = {
            "url": self.url,
            "sha-256": self.sha256,
            "friendlyVersion": self.version,
            "timestamp": self.timestamp,
            "notes": self.notes if self.notes else self.version,
        }
        if archival:
            result["kind"] = self.kind
            result["hardware"] = self.hardware
        return result

    @classmethod
    def upsert(cls, hardware, kind, version, url, sha256, timestamp, notes):
        existing = cls.query.filter_by(hardware=hardware, kind=kind, version=version).one_or_none()
        if existing is None:
            db.session.add(
                cls(
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


db.Index(
    "ix_firmwares_hardware_kind_timestamp",
    Firmware.hardware,
    Firmware.kind,
    Firmware.timestamp.desc(),
)


def init_app(app):
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    migrate.init_app(app, db)
