from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rentals = db.relationship('Rental', backref='user', lazy=True)


class Distribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)      # ex: "ubuntu-22.04"
    docker_image = db.Column(db.String(128), nullable=False)          # ex: "iac-project/ubuntu-22.04-ssh"
    version = db.Column(db.String(32))
    status = db.Column(db.String(20), default='active')               # active | disabled


class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(128), unique=True, nullable=False)
    ip = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default='AVAILABLE')            # AVAILABLE | BUSY | OFFLINE
    cpu = db.Column(db.String(32))
    memory = db.Column(db.String(32))
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)

    instances = db.relationship('Instance', backref='worker', lazy=True)


class Instance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.String(128))
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    distribution_id = db.Column(db.Integer, db.ForeignKey('distribution.id'), nullable=False)
    ssh_port = db.Column(db.Integer)
    status = db.Column(db.String(20), default='running')              # running | stopped | unreachable
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    distribution = db.relationship('Distribution')
    rental = db.relationship('Rental', backref='instance', uselist=False)


class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    instance_id = db.Column(db.Integer, db.ForeignKey('instance.id'), unique=True, nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')                # active | expired | terminated