import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-cambia-esto")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False


"""import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Base de datos local SQLite (archivo sop.db junto a config.py)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'sop.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Necesario para sesiones / formularios
    SECRET_KEY = 'cambia_esta_clave_luego'"""