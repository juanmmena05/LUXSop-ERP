from flask import Flask
from config import Config        # carga Config desde config.py en la raíz
from .models import db           # importa la instancia de SQLAlchemy
from .routes import main_bp      # importa el blueprint de rutas


# app/__init__.py
from flask import Flask
from .models import db
from config import Config  # <- si config.py está en la raíz del proyecto

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        # 👇 IMPORTA el módulo completo para registrar TODAS las clases de modelos
        from . import models
        # Si no usas /initdb y quieres crear aquí, descomenta:
        # db.create_all()

        # Registra blueprints después de init_app
        from .routes import main_bp
        app.register_blueprint(main_bp)

    return app
