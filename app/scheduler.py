from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from app.extensions import db
from app.models import Rental, Instance, Worker
from app.resource_manager import (
    check_instance_status, repair_instance, teardown_instance,
    migrate_instance_to_new_worker, NoWorkerAvailableError,
    PENDING_NOTIFICATIONS,
)

WORKER_HEARTBEAT_TIMEOUT = 60  # secondes ; 3x l'intervalle de heartbeat (20s) pour tolérer un aléa réseau


def _check_instance_health(app):
    """Vérifie chaque instance active dont le Worker est sain, répare si besoin."""
    with app.app_context():
        rentals = Rental.query.filter_by(status='active').all()

        for rental in rentals:
            instance = rental.instance
            if instance is None or instance.worker is None or instance.worker.status != 'AVAILABLE':
                continue  # Worker OFFLINE : c'est _check_workers qui gère la migration

            status = check_instance_status(instance)
            instance.status = status

            if status == 'unreachable':
                if repair_instance(instance):
                    app.logger.info(f"Instance {instance.id} réparée sur son Worker actuel")
                else:
                    app.logger.error(f"Échec de réparation de l'instance {instance.id}")

        db.session.commit()


def _check_workers(app):
    """Détecte les Workers dont le heartbeat est trop ancien et migre leurs instances."""
    with app.app_context():
        threshold = datetime.utcnow() - timedelta(seconds=WORKER_HEARTBEAT_TIMEOUT)
        stale_workers = Worker.query.filter(
            Worker.status != 'OFFLINE',
            Worker.last_heartbeat < threshold,
        ).all()

        for worker in stale_workers:
            app.logger.warning(
                f"Worker {worker.hostname} déclaré OFFLINE "
                f"(dernier heartbeat : {worker.last_heartbeat})"
            )
            worker.status = 'OFFLINE'
            _migrate_instances_from(worker, app)

        db.session.commit()


def _migrate_instances_from(worker, app):
    affected = Instance.query.filter_by(worker_id=worker.id) \
        .filter(Instance.status != 'stopped').all()

    for instance in affected:
        rental = instance.rental
        if rental is None or rental.status != 'active':
            continue

        try:
            result = migrate_instance_to_new_worker(instance.distribution)
        except NoWorkerAvailableError:
            app.logger.error(
                f"Migration impossible pour l'instance {instance.id} : aucun Worker disponible"
            )
            instance.status = 'stopped'
            continue

        old_worker_id = instance.worker_id
        instance.worker_id = result['worker_id']
        instance.container_id = result['instance_key']
        instance.ssh_port = result['ssh_port']
        instance.status = 'running'

        # Nouvelle clé SSH : à afficher une seule fois au prochain accès au dashboard
        PENDING_NOTIFICATIONS[rental.id] = {
            'private_key': result['private_key'],
            'ssh_host': result['ssh_host'],
        }

        app.logger.info(
            f"Instance {instance.id} migrée du Worker {old_worker_id} "
            f"vers le Worker {result['worker_id']}"
        )


def _cleanup_expired_rentals(app):
    with app.app_context():
        expired = Rental.query.filter(
            Rental.status == 'active',
            Rental.end_time <= datetime.utcnow(),
        ).all()

        for rental in expired:
            if rental.instance is not None and rental.instance.worker is not None:
                if not teardown_instance(rental.instance):
                    app.logger.error(f"Échec du teardown de l'instance {rental.instance.id}")
                    continue
                rental.instance.status = 'stopped'

            rental.status = 'expired'
            app.logger.info(f"Location {rental.id} terminée (expiration).")

        db.session.commit()


def init_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=_check_instance_health, args=[app],
                       trigger='interval', seconds=45, id='instance_health_check')
    scheduler.add_job(func=_check_workers, args=[app],
                       trigger='interval', seconds=30, id='worker_health_check')
    scheduler.add_job(func=_cleanup_expired_rentals, args=[app],
                       trigger='interval', seconds=60, id='expiration_cleanup')
    scheduler.start()
    return scheduler