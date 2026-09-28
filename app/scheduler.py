from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from app.extensions import db
from app.models import Rental, InstanceState
from app.orchestrator import check_status, repair, teardown, ProvisioningError, TeardownError

MAX_REPAIR_ATTEMPTS = 3


def _check_active_rentals(app):
    """Vérifie chaque location active et répare si besoin. Tourne toutes les 30-60s."""
    with app.app_context():
        rentals = Rental.query.filter_by(status='active').all()

        for rental in rentals:
            state = rental.instance_state
            if state is None:
                continue  # ne devrait pas arriver, mais on ne casse rien si c'est le cas

            result = check_status(rental.instance_id)
            state.last_status = result['status']
            state.last_checked_at = datetime.utcnow()

            if result['status'] == 'unreachable':
                if state.repair_attempts >= MAX_REPAIR_ATTEMPTS:
                    rental.status = 'terminated'
                    app.logger.warning(
                        f"Instance {rental.instance_id} abandonnée après "
                        f"{MAX_REPAIR_ATTEMPTS} tentatives de réparation."
                    )
                else:
                    try:
                        repair(rental.instance_id)
                        state.repair_attempts += 1
                        app.logger.info(f"Réparation tentée sur {rental.instance_id}")
                    except ProvisioningError as e:
                        app.logger.error(f"Échec de réparation sur {rental.instance_id} : {e}")
            else:
                state.repair_attempts = 0  # remise à zéro dès que l'instance répond de nouveau

        db.session.commit()


def _cleanup_expired_rentals(app):
    """Termine et nettoie les locations dont la durée est dépassée."""
    with app.app_context():
        expired = Rental.query.filter(
            Rental.status == 'active',
            Rental.expires_at <= datetime.utcnow(),
        ).all()

        for rental in expired:
            try:
                teardown(rental.instance_id)
            except TeardownError as e:
                app.logger.error(f"Échec du teardown de {rental.instance_id} : {e}")
                continue  # on retentera au prochain cycle plutôt que de marquer 'expired' à tort

            rental.status = 'expired'
            app.logger.info(f"Location {rental.instance_id} terminée (expiration).")

        db.session.commit()


def init_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=_check_active_rentals, args=[app],
        trigger='interval', seconds=45, id='health_check',
    )
    scheduler.add_job(
        func=_cleanup_expired_rentals, args=[app],
        trigger='interval', seconds=60, id='expiration_cleanup',
    )
    scheduler.start()
    return scheduler