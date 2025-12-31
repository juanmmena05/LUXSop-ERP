# seed_users.py
from app import create_app
from app.extensions import db
from app.models import User, Personal
from typing import Optional


app = create_app()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin123!"   # cámbiala

# operativos a crear: (username, password, personal_id)
# recomendación: usa username = personal_id para fácil acceso
OPERATIVOS = [
    ("L0036", "Oper123!", "L0036"),
    ("L0082", "Oper123!", "L0082"),
    ("L0212", "Oper123!", "L0212"),
]


def upsert_user(username: str, password: str, role: str, personal_id: Optional[str] = None) -> User:
    u = User.query.filter_by(username=username).first()

    if u:
        # actualizar
        u.role = role
        u.personal_id = personal_id
        if password:
            u.set_password(password)
        return u

    # crear
    u = User(username=username, role=role, personal_id=personal_id)
    u.set_password(password)
    db.session.add(u)
    return u

with app.app_context():
    # 1) admin
    upsert_user(ADMIN_USERNAME, ADMIN_PASSWORD, "admin", None)

    # 2) operativos (deben existir en Personal)
    for username, pwd, pid in OPERATIVOS:
        p = Personal.query.filter_by(personal_id=pid).first()
        if not p:
            raise RuntimeError(
                f"❌ No existe Personal con personal_id={pid}. "
                f"Primero importa Personal desde Excel y luego corre seed_users.py"
            )

        # valida que no haya OTRO user ya ligado a ese personal (por unique=True)
        existing_link = User.query.filter(User.personal_id == pid, User.username != username).first()
        if existing_link:
            raise RuntimeError(
                f"❌ El personal_id={pid} ya está ligado al usuario '{existing_link.username}'. "
                f"No puede haber 2 usuarios para el mismo Personal."
            )

        upsert_user(username, pwd, "operativo", pid)

    db.session.commit()
    print("✅ Usuarios creados/actualizados:")
    print(f"   - admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    for username, pwd, pid in OPERATIVOS:
        print(f"   - operativo: {username} / {pwd} (personal_id={pid})")
