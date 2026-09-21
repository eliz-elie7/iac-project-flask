from flask import Flask
from app.extensions import db, migrate, login_manager
from app.models import User

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-me-in-.env'
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'postgresql://iac_user:iac_pass@db:5432/iac_project'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.auth import auth_bp
    from app.dashboard import dashboard_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)