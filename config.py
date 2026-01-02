import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-cambia-esto")

    # 1) Producción / docker-compose / Azure: usa DATABASE_URL
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL:
        # Heroku-style compatibility: postgres:// -> postgresql://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # 2) Fallback dev: SQLite (persistible si DB_PATH está)
        DB_PATH = os.environ.get("DB_PATH")  # ej: /data/app.db
        if DB_PATH:
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + DB_PATH
        else:
            SQLALCHEMY_DATABASE_URI = "sqlite:///app.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
