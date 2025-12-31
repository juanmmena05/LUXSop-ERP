from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    import app.models
    db.create_all()
    print("✅ Tablas creadas")
