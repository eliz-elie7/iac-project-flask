import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.extensions import db
from app.models import Rental
from app import orchestrator


_scheduler = BackgroundScheduler(daemon=True)


def reconcile_instances(app):
    with app.app_context():
        rentals = Rental.query.filter_by(status="active").all()
        now = datetime.utcnow()

        for rental in rentals:
            state = rental.instance_state
            if state is None:
                continue

            if rental.expires_at <= now:
                try:
                    orchestrator.teardown(rental.instance_id)
                except Exception:
                    state.last_status = "teardown_failed"
                else:
                    rental.status = "expired"
                    state.last_status = "expired"
                state.last_checked_at = now
                continue

            status = orchestrator.check_status(
                rental.instance_id,
                state.ssh_host,
                state.ssh_port,
            )
            state.last_checked_at = now

            if status["status"] == "running":
                state.last_status = "running"
                continue

            state.last_status = "repairing"
            state.repair_attempts = (state.repair_attempts or 0) + 1
            try:
                repaired = orchestrator.repair(rental.instance_id)
            except Exception:
                state.last_status = "unreachable"
            else:
                state.ssh_port = repaired.get("ssh_port", state.ssh_port)
                state.last_status = "running"

        db.session.commit()


def start_scheduler(app):
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if _scheduler.running:
        return

    _scheduler.add_job(
        reconcile_instances,
        "interval",
        seconds=30,
        args=[app],
        id="reconcile-instances",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
