from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user

from app.models import Rental
from app.resource_manager import terminate_rental

instances_bp = Blueprint('instances', __name__)


def _get_owned_rental(rental_id):
    """404 (pas 403) si la location n'existe pas ou n'appartient pas à l'utilisateur —
    on évite de révéler qu'un identifiant existe mais appartient à quelqu'un d'autre."""
    rental = Rental.query.filter_by(id=rental_id, user_id=current_user.id).first()
    if rental is None:
        abort(404)
    return rental


@instances_bp.route('/instances', methods=['GET'])
@login_required
def list_instances():
    return jsonify([
        {
            "rental_id": r.id,
            "distribution": r.instance.distribution.name if r.instance else None,
            "status": r.status,
            "ssh_port": r.instance.ssh_port if r.instance else None,
            "end_time": r.end_time.isoformat(),
        }
        for r in current_user.rentals
    ])


@instances_bp.route('/instances/<int:rental_id>/stop', methods=['POST'])
@login_required
def stop_instance(rental_id):
    rental = _get_owned_rental(rental_id)

    if rental.status != 'active':
        return jsonify({"error": "Cette location n'est plus active."}), 400

    if not terminate_rental(rental):
        return jsonify({"error": "Échec de l'arrêt de l'instance."}), 500

    return jsonify({"status": "terminated"})