# manage.py
from app import create_app
from app.models import db

app = create_app()

with app.app_context():
    # 👇 Importa el módulo para registrar TODAS las clases de modelos
    from app import models  # noqa: F401
    print("DB URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))
    db.create_all()
    print("✅ Tablas creadas o actualizadas correctamente.")
