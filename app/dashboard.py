from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Rental, InstanceState
from app import orchestrator

dashboard_bp = Blueprint('dashboard', __name__)

DISTRIBUTIONS = ["ubuntu-22.04", "debian-12"]


@dashboard_bp.route('/')
@login_required
def index():
    return render_template('dashboard.html', rentals=current_user.rentals)


@dashboard_bp.route('/rent', methods=['GET', 'POST'])
@login_required
def rent():
    if request.method == 'GET':
        return render_template('rent.html', distributions=DISTRIBUTIONS)

    distribution = request.form.get('distribution')
    duration_hours = request.form.get('duration_hours', type=int)

    if distribution not in DISTRIBUTIONS or not duration_hours or duration_hours <= 0:
        flash("Distribution ou durée invalide.")
        return redirect(url_for('dashboard.rent'))

    try:
        result = orchestrator.provision(current_user.id, distribution, duration_hours)
    except orchestrator.ProvisioningError as e:
        flash(f"Échec du provisionnement : {e}")
        return redirect(url_for('dashboard.rent'))
    except orchestrator.TimeoutError:
        flash("L'instance n'a pas répondu à temps. Réessaie.")
        return redirect(url_for('dashboard.rent'))

    rental = Rental(
        user_id=current_user.id,
        instance_id=result['instance_id'],
        distribution=distribution,
        duration_hours=duration_hours,
        expires_at=datetime.utcnow() + timedelta(hours=duration_hours),
        status='active',
    )
    db.session.add(rental)
    db.session.flush()  # récupère rental.id avant de créer InstanceState

    instance_state = InstanceState(
        rental_id=rental.id,
        ssh_host=result['ssh_host'],
        ssh_port=result['ssh_port'],
        last_status='running',
    )
    db.session.add(instance_state)
    db.session.commit()

    # La clé privée n'est jamais stockée en base : elle n'existe que dans
    # ce résultat mémoire et sur cette page, affichée une seule fois.
    return render_template(
        'key_reveal.html',
        rental=rental,
        ssh_host=result['ssh_host'],
        ssh_port=result['ssh_port'],
        private_key=result['private_key'],
    )