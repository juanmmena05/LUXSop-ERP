#!/bin/sh
set -e

python - <<'PY'
import os, time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
if url:
    # compat postgres://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Espera a que Postgres responda
    for i in range(30):
        try:
            eng = create_engine(url, pool_pre_ping=True)
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            break
        except Exception as e:
            time.sleep(2)
    else:
        raise RuntimeError("DB no disponible (timeout)")

from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    db.create_all()
    print("✅ create_all listo")
PY

exec "$@"
