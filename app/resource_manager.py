import uuid
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models import Worker, Instance

resource_bp = Blueprint('resource_manager', __name__)

WORKER_PORT = 6000

# Notifications éphémères (jamais persistées) : rental_id -> {private_key, ssh_host}
# Utilisé quand une instance est migrée suite à une panne de Worker.
PENDING_NOTIFICATIONS = {}

class NoWorkerAvailableError(Exception):
    pass

class ProvisioningError(Exception):
    pass


# ---------- Endpoints appelés par les Worker Agents ----------

@resource_bp.route('/workers/register', methods=['POST'])
def register_worker():
    data = request.get_json()
    worker = Worker.query.filter_by(hostname=data['hostname']).first()

    if worker is None:
        worker = Worker(
            hostname=data['hostname'],
            ip=data['ip'],
            cpu=data.get('cpu'),
            memory=data.get('memory'),
            status='AVAILABLE',
        )
        db.session.add(worker)
    else:
        # Redémarrage de l'agent sur un Worker déjà connu : on le remet en ligne
        worker.ip = data['ip']
        worker.status = 'AVAILABLE'
        worker.last_heartbeat = datetime.utcnow()

    db.session.commit()
    return jsonify({"worker_id": worker.id})


@resource_bp.route('/workers/heartbeat', methods=['POST'])
def worker_heartbeat():
    data = request.get_json()
    worker = Worker.query.get(data['worker_id'])
    if worker is None:
        return jsonify({"error": "Worker inconnu, ré-enregistrement nécessaire"}), 404

    worker.last_heartbeat = datetime.utcnow()
    worker.cpu = data.get('cpu', worker.cpu)
    worker.memory = data.get('memory', worker.memory)
    # Ne pas écraser BUSY si le Resource Manager vient d'assigner ce Worker
    # entre deux battements de coeur
    if worker.status != 'BUSY':
        worker.status = 'AVAILABLE'

    db.session.commit()
    return jsonify({"status": "ok"})


# ---------- Endpoints de consultation (API publique) ----------

@resource_bp.route('/workers', methods=['GET'])
def list_workers():
    return jsonify([_worker_to_dict(w) for w in Worker.query.all()])


@resource_bp.route('/workers/<int:worker_id>', methods=['GET'])
def get_worker(worker_id):
    return jsonify(_worker_to_dict(Worker.query.get_or_404(worker_id)))


def _worker_to_dict(w):
    return {
        "id": w.id, "hostname": w.hostname, "ip": w.ip,
        "status": w.status, "cpu": w.cpu, "memory": w.memory,
        "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
    }


# ---------- Logique interne du Resource Manager ----------

def _select_available_worker() -> Worker:
    worker = Worker.query.filter_by(status='AVAILABLE') \
        .order_by(Worker.last_heartbeat.desc()).first()
    if worker is None:
        raise NoWorkerAvailableError("Aucun Worker disponible actuellement")
    return worker


def provision_on_best_worker(distribution) -> dict:
    worker = _select_available_worker()
    worker.status = 'BUSY'
    db.session.commit()

    instance_key = uuid.uuid4().hex[:8]
    try:
        resp = requests.post(
            f"http://{worker.hostname}:{WORKER_PORT}/internal/provision",
            json={"instance_id": instance_key, "docker_image": distribution.docker_image},
            timeout=60,
        )
        if resp.status_code != 200:
            # On récupère le vrai message d'erreur renvoyé par l'agent, si présent
            try:
                detail = resp.json().get('error', resp.text)
            except ValueError:
                detail = resp.text
            raise ProvisioningError(f"Worker {worker.hostname} : {detail}")
        result = resp.json()
    finally:
        worker.status = 'AVAILABLE'
        db.session.commit()

    result['worker_id'] = worker.id
    result['instance_key'] = instance_key
    return result


def check_instance_status(instance: Instance) -> str:
    try:
        resp = requests.get(
            f"http://{instance.worker.hostname}:{WORKER_PORT}/internal/status/{instance.container_id}",
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()['status']
    except requests.RequestException:
        return 'unreachable'


def repair_instance(instance: Instance) -> bool:
    try:
        resp = requests.post(
            f"http://{instance.worker.hostname}:{WORKER_PORT}/internal/repair/{instance.container_id}",
            timeout=30,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def teardown_instance(instance: Instance) -> bool:
    try:
        resp = requests.post(
            f"http://{instance.worker.hostname}:{WORKER_PORT}/internal/teardown/{instance.container_id}",
            timeout=30,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def migrate_instance_to_new_worker(distribution) -> dict:
    """Utilisé quand le Worker hébergeant une instance est OFFLINE :
    provisionne une instance de remplacement sur un autre Worker disponible."""
    return provision_on_best_worker(distribution)