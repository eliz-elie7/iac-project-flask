from datetime import datetime
from flask_login import UserMixin
from app.extensions import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rentals = db.relationship('Rental', backref='user', lazy=True)


class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    instance_id = db.Column(db.String(64), unique=True, nullable=False)
    distribution = db.Column(db.String(64), nullable=False)
    duration_hours = db.Column(db.Integer, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')

    instance_state = db.relationship('InstanceState', backref='rental', uselist=False)


class InstanceState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_id = db.Column(db.Integer, db.ForeignKey('rental.id'), unique=True, nullable=False)
    ssh_host = db.Column(db.String(120))
    ssh_port = db.Column(db.Integer)
    last_status = db.Column(db.String(20), default='running')
    last_checked_at = db.Column(db.DateTime, default=datetime.utcnow)
    repair_attempts = db.Column(db.Integer, default=0)