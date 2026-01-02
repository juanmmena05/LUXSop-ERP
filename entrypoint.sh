#!/bin/sh
set -e

python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")

print("[DEBUG] =================================================", flush=True)
print(f"[DEBUG] DATABASE_URL presente: {bool(url)}", flush=True)

if url:
    # Mostrar URL sanitizada (sin password)
    if "@" in url:
        parts = url.split("@")
        user_part = parts[0].split("://")[1].split(":")[0]
        host_part = "@".join(parts[1:])
        safe_url = f"postgresql://{user_part}:***@{host_part}"
        print(f"[DEBUG] Connection string: {safe_url}", flush=True)
    
    # compat postgres://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        print("[DEBUG] Convertido postgres:// a postgresql://", flush=True)

    # Espera a que Postgres responda
    print("[DEBUG] Iniciando intentos de conexión (max 30)...", flush=True)
    last_error = None
    
    for i in range(30):
        try:
            print(f"[ATTEMPT {i+1}/30] Conectando a PostgreSQL...", flush=True)
            eng = create_engine(url, pool_pre_ping=True)
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            print("[SUCCESS] ✅ Conexión exitosa a PostgreSQL", flush=True)
            break
        except Exception as e:
            last_error = e
            error_type = type(e).__name__
            error_msg = str(e)
            
            print(f"[ERROR] {error_type}: {error_msg}", flush=True)
            
            # Diagnóstico específico
            if "could not translate host name" in error_msg or "Name or service not known" in error_msg:
                print("[DIAGNOSIS] ❌ DNS: No se puede resolver el hostname", flush=True)
            elif "Connection refused" in error_msg:
                print("[DIAGNOSIS] ❌ NETWORK: Puerto 5432 cerrado o bloqueado", flush=True)
            elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                print("[DIAGNOSIS] ❌ FIREWALL: Timeout - posible bloqueo de red", flush=True)
            elif "SSL" in error_msg or "certificate" in error_msg or "ssl" in error_msg.lower():
                print("[DIAGNOSIS] ❌ SSL: Error de certificados o handshake", flush=True)
            elif "password authentication failed" in error_msg:
                print("[DIAGNOSIS] ❌ AUTH: Usuario o contraseña incorrectos", flush=True)
            elif "no pg_hba.conf entry" in error_msg:
                print("[DIAGNOSIS] ❌ FIREWALL: IP no permitida en PostgreSQL", flush=True)
            elif "database" in error_msg.lower() and "does not exist" in error_msg.lower():
                print("[DIAGNOSIS] ❌ DATABASE: La base de datos no existe", flush=True)
            
            if i < 29:
                print(f"[WAIT] Reintentando en 2 segundos...\n", flush=True)
                time.sleep(2)
    else:
        print("\n" + "="*60, flush=True)
        print("[FATAL] ❌ NO SE PUDO CONECTAR A POSTGRESQL", flush=True)
        print("="*60, flush=True)
        if last_error:
            print(f"[FATAL] Último error: {type(last_error).__name__}", flush=True)
            print(f"[FATAL] Mensaje: {str(last_error)}", flush=True)
            print(f"[FATAL] Repr: {repr(last_error)}", flush=True)
        print("="*60 + "\n", flush=True)
        sys.exit(1)

    # Crear tablas
    print("[DEBUG] Importando create_app...", flush=True)
    from app import create_app
    from app.extensions import db
    
    print("[DEBUG] Creando app context...", flush=True)
    app = create_app()
    
    with app.app_context():
        print("[DEBUG] Ejecutando db.create_all()...", flush=True)
        db.create_all()
        print("✅ create_all listo", flush=True)
else:
    print("[WARNING] DATABASE_URL no configurada - saltando DB check", flush=True)

print("[DEBUG] =================================================\n", flush=True)
PY

exec "$@"