from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Rental, InstanceState
from app.orchestrator import provision, ProvisioningError

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    return render_template('dashboard.html', rentals=current_user.rentals)


@dashboard_bp.route('/rent', methods=['GET', 'POST'])
@login_required
def rent():
    if request.method == 'POST':
        distribution = request.form['distribution']
        duration_hours = int(request.form['duration_hours'])

        try:
            result = provision(current_user.id, distribution, duration_hours)
        except ProvisioningError as e:
            flash(f"Échec de la création de l'instance : {e}")
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
        db.session.flush()  # récupère rental.id avant le commit final

        state = InstanceState(
            rental_id=rental.id,
            ssh_host=result['ssh_host'],
            ssh_port=result['ssh_port'],
            last_status='running',
        )
        db.session.add(state)
        db.session.commit()

        # La clé privée n'est affichée qu'ici, une seule fois. Jamais stockée.
        return render_template(
            'rental_created.html',
            rental=rental,
            private_key=result['private_key'],
        )

    return render_template('rent.html')