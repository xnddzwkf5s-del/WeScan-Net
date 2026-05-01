from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # Trust nginx reverse proxy for HTTPS/scheme detection
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wescan.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_page'
    login_manager.login_message = None
    migrate.init_app(app, db)

    # Register blueprints
    from app.routes.auth import auth
    from app.routes.dashboard import dashboard
    from app.routes.smtp import smtp
    from app.routes.admin import admin
    from app.routes.payments import payments
    from app.routes.pdf_edit import pdf_edit
    from app.api import api_bp

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(smtp)
    app.register_blueprint(admin)
    app.register_blueprint(payments)
    app.register_blueprint(pdf_edit)
    app.register_blueprint(api_bp)

    # User loader
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app
