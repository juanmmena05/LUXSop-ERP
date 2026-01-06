import os
import sys
from sqlalchemy import text

# Connection string de Azure PostgreSQL
DATABASE_URL = "postgresql+psycopg2://sop_user:SopSecure2024@sop-pg-18964.postgres.database.azure.com:5432/sop_app?sslmode=require"

# Importar módulos de tu app
sys.path.insert(0, os.path.dirname(__file__))
from import_excels import (
    CFG, IMPORT_ORDER, load_df, upsert_table
)
from app import create_app, db
from app.models import (
    SopFraccionDetalle, SopFraccion, ElementoDetalle, ElementoSet, Elemento,
    RecetaDetalle, Receta, Quimico, KitDetalle, Kit, Herramienta,
    MetodologiaBasePaso, Metodologia, MetodologiaBase, Consumo, Fraccion,
    SOP, SubArea, Area, User, Personal, NivelLimpieza
)

def reset_db_azure():
    """Borrar datos en orden seguro"""
    print("🗑️  Borrando datos de Azure PostgreSQL...")
    
    db.session.query(SopFraccionDetalle).delete(synchronize_session=False)
    db.session.query(SopFraccion).delete(synchronize_session=False)
    
    db.session.query(ElementoDetalle).delete(synchronize_session=False)
    db.session.query(ElementoSet).delete(synchronize_session=False)
    db.session.query(Elemento).delete(synchronize_session=False)
    
    db.session.query(RecetaDetalle).delete(synchronize_session=False)
    db.session.query(Receta).delete(synchronize_session=False)
    db.session.query(Quimico).delete(synchronize_session=False)
    
    db.session.query(KitDetalle).delete(synchronize_session=False)
    db.session.query(Kit).delete(synchronize_session=False)
    db.session.query(Herramienta).delete(synchronize_session=False)
    
    db.session.query(MetodologiaBasePaso).delete(synchronize_session=False)
    db.session.query(Metodologia).delete(synchronize_session=False)
    db.session.query(MetodologiaBase).delete(synchronize_session=False)
    
    db.session.query(Consumo).delete(synchronize_session=False)
    db.session.query(Fraccion).delete(synchronize_session=False)
    
    db.session.query(SOP).delete(synchronize_session=False)
    db.session.query(SubArea).delete(synchronize_session=False)
    db.session.query(Area).delete(synchronize_session=False)
    
    db.session.query(User).delete(synchronize_session=False)
    db.session.query(Personal).delete(synchronize_session=False)
    db.session.query(NivelLimpieza).delete(synchronize_session=False)
    
    db.session.commit()
    print("   ✅ Datos borrados exitosamente")

def main():
    # Crear app
    app = create_app()
    
    # ✅ FORZAR configuración de Azure PostgreSQL
    print(f"🔍 Configurando conexión a Azure...")
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    app.config['SQLALCHEMY_BINDS'] = None
    
    with app.app_context():
        # Verificar conexión
        try:
            result = db.session.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            
            if 'PostgreSQL' in version:
                print(f"✅ Conectado a PostgreSQL Azure")
                print(f"   Versión: {version.split(',')[0]}")
            else:
                print(f"❌ ERROR: Conectado a BD incorrecta")
                print(f"   {version}")
                return
                
        except Exception as e:
            print(f"❌ Error de conexión: {e}")
            import traceback
            traceback.print_exc()
            return
        
        print("\n⚠️  ADVERTENCIA: Esto borrará TODOS los datos de Azure PostgreSQL")
        print("   Base de datos: sop-pg-18964.postgres.database.azure.com")
        print("   Esto afectará tu app web: https://transformandclean.com")
        print("")
        confirm = input("¿Estás seguro? Escribe 'SI' para continuar: ")
        
        if confirm != "SI":
            print("❌ Operación cancelada")
            return
        
        try:
            # Borrar datos
            reset_db_azure()
            
            # Importar Excel
            print("\n📊 Importando Excel desde /imports...")
            import_dir = os.path.join(os.path.dirname(__file__), 'imports')
            
            if not os.path.exists(import_dir):
                print(f"❌ No se encontró la carpeta: {import_dir}")
                return
            
            total_inserted = 0
            total_updated = 0
            
            for table_name in IMPORT_ORDER:
                try:
                    df = load_df(import_dir, table_name)
                    
                    if df.empty:
                        print(f"   ⏭️  {table_name}: sin datos en Excel")
                        continue
                    
                    print(f"   📄 {table_name}: {len(df)} filas leídas del Excel")
                    
                    ins, upd = upsert_table(df, table_name)
                    db.session.commit()
                    
                    total_inserted += ins
                    total_updated += upd
                    
                    status = []
                    if ins > 0:
                        status.append(f"+{ins} nuevos")
                    if upd > 0:
                        status.append(f"~{upd} actualizados")
                    
                    print(f"   ✅ {table_name}: {', '.join(status) if status else 'sin cambios'}")
                    
                except Exception as e:
                    db.session.rollback()
                    print(f"   ❌ Error en {table_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
            
            # Verificar datos en BD
            print("\n🔍 Verificando datos en Azure PostgreSQL...")
            try:
                fraccion_count = db.session.execute(text("SELECT COUNT(*) FROM fraccion")).scalar()
                elemento_count = db.session.execute(text("SELECT COUNT(*) FROM elemento")).scalar()
                print(f"   📊 Fracciones en BD: {fraccion_count}")
                print(f"   📊 Elementos en BD: {elemento_count}")
            except Exception as e:
                print(f"   ⚠️  No se pudo verificar: {e}")
            
            print("\n" + "="*70)
            print("🎉 Base de datos de Azure actualizada exitosamente!")
            print(f"   📥 {total_inserted} registros insertados")
            print(f"   📝 {total_updated} registros actualizados")
            print("="*70)
            print("\n✅ Tu app web ya tiene los datos actualizados:")
            print("   🌐 https://transformandclean.com")
            print("   🌐 https://www.transformandclean.com")
            print("="*70)
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error durante la actualización: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()