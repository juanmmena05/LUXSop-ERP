# __init__.py - Registro de blueprints modular
#
# Blueprints organizados por dominio:
# - auth_bp: login, logout
# - home_bp: home, admin panel
# - rutas_bp: mi_ruta, plan_dia, ruta_dia, asignaciones
# - reportes_bp: reportes HTML y PDF
# - plantillas_bp: gestión de plantillas
# - sop_bp: gestión de SOP (regular, consecuente, evento)
# - catalogos_bp: páginas de catálogos (HTML)
# - api_bp: APIs REST (tareas, químicos, recetas, elementos, fracciones, etc.)
#

from .auth import auth_bp
from .home import home_bp
from .rutas_bp import rutas_bp
from .reportes_bp import reportes_bp
from .plantillas_bp import plantillas_bp
from .sop_bp import sop_bp
from .catalogos_bp import catalogos_bp
from .api_bp import api_bp
from .visor_bp import visor_bp


def register_blueprints(app):
    """Registra todos los blueprints en la aplicación Flask"""
    # Blueprints modulares
    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(rutas_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(plantillas_bp)
    app.register_blueprint(sop_bp)
    app.register_blueprint(catalogos_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(visor_bp) 
    
