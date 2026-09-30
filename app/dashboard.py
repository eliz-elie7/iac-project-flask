from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Rental, Instance, Distribution
from app.resource_manager import provision_on_best_worker, NoWorkerAvailableError

dashboard_bp = Blueprint('dashboard', __name__)

from app.resource_manager import PENDING_NOTIFICATIONS

@dashboard_bp.route('/')
@login_required
def index():
    notification = None
    for rental in current_user.rentals:
        if rental.id in PENDING_NOTIFICATIONS:
            notification = PENDING_NOTIFICATIONS.pop(rental.id)
            notification['rental_id'] = rental.id
            break  # une seule notification affichée à la fois, simple pour un prototype

    return render_template('dashboard.html', rentals=current_user.rentals, notification=notification)


@dashboard_bp.route('/rent', methods=['GET', 'POST'])
@login_required
def rent():
    if request.method == 'POST':
        distribution = Distribution.query.filter_by(
            name=request.form['distribution'], status='active'
        ).first()
        if distribution is None:
            flash("Distribution invalide.")
            return redirect(url_for('dashboard.rent'))

        duration_hours = int(request.form['duration_hours'])

        try:
            result = provision_on_best_worker(distribution)
        except NoWorkerAvailableError as e:
            flash(f"Impossible de louer une instance : {e}")
            return redirect(url_for('dashboard.rent'))
        except Exception as e:
            flash(f"Échec du provisioning : {e}")
            return redirect(url_for('dashboard.rent'))

        instance = Instance(
            container_id=result['instance_key'],
            worker_id=result['worker_id'],
            distribution_id=distribution.id,
            ssh_port=result['ssh_port'],
            status='running',
        )
        db.session.add(instance)
        db.session.flush()  # récupère instance.id avant le commit final

        rental = Rental(
            user_id=current_user.id,
            instance_id=instance.id,
            end_time=datetime.utcnow() + timedelta(hours=duration_hours),
            status='active',
        )
        db.session.add(rental)
        db.session.commit()

        # La clé privée n'est affichée qu'ici, une seule fois. Jamais stockée.
        return render_template(
            'rental_created.html',
            rental=rental,
            ssh_host=result['ssh_host'],
            private_key=result['private_key'],
        )

    distributions = Distribution.query.filter_by(status='active').all()
    return render_template('rent.html', distributions=distributions)