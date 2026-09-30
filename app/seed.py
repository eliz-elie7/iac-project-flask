from app.extensions import db
from app.models import Distribution

def seed_distributions():
    defaults = [
        {"name": "ubuntu-22.04", "docker_image": "iac-project/ubuntu-22.04-ssh", "version": "22.04"},
        {"name": "debian-12", "docker_image": "iac-project/debian-12-ssh", "version": "12"},
    ]
    for d in defaults:
        if not Distribution.query.filter_by(name=d["name"]).first():
            db.session.add(Distribution(**d))
    db.session.commit()