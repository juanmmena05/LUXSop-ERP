from flask import Flask
from config import Config
from .extensions import db, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # ✅ init login
    login_manager.init_app(app)
    login_manager.login_view = "main.login"   # endpoint del login en tu blueprint

    with app.app_context():
        from . import models  # registra modelos (incluye User)
        from .models import User
        from .routes import main_bp
        app.register_blueprint(main_bp)

        @login_manager.user_loader
        def load_user(user_id: str):
            return User.query.get(int(user_id))

    return app
