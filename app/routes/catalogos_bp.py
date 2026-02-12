# catalogos_bp.py - Blueprint para páginas de catálogos
#
# Rutas HTML para gestión de catálogos:
# - Compartidos: químicos-recetas, consumos
# - Regulares: elementos, herramientas, kits, fracciones, metodologías
# - Eventos: kits-eventos, fracciones-eventos, metodologías-eventos

import json
from flask import Blueprint, render_template, redirect, url_for, flash
from sqlalchemy.orm import joinedload

from ..models import (
    db, Quimico, Receta, RecetaDetalle, Consumo, Fraccion,
    EventoCatalogo, SopEventoFraccion, MetodologiaEventoFraccion
)
from .helpers import admin_required


catalogos_bp = Blueprint("catalogos", __name__)


# =========================
# COMPARTIDOS
# =========================

@catalogos_bp.route("/catalogos/quimicos-recetas")
@admin_required
def quimicos_recetas():
    """Panel unificado para gestionar Químicos y Recetas"""
    quimicos = Quimico.query.order_by(Quimico.nombre.asc()).all()

    recetas = (
        Receta.query
        .options(joinedload(Receta.detalles).joinedload(RecetaDetalle.quimico))
        .order_by(Receta.nombre.asc())
        .all()
    )

    recetas_list = []
    for r in recetas:
        receta_data = {
            'receta_id': r.receta_id,
            'nombre': r.nombre,
            'detalles': []
        }

        for d in r.detalles:
            detalle_data = {
                'quimico_id': d.quimico_id,
                'dosis': float(d.dosis) if d.dosis else 0,
                'unidad_dosis': d.unidad_dosis or '',
                'volumen_base': float(d.volumen_base) if d.volumen_base else 0,
                'unidad_volumen': d.unidad_volumen or '',
                'nota': d.nota or ''
            }
            receta_data['detalles'].append(detalle_data)

        recetas_list.append(receta_data)

    recetas_json_str = json.dumps(recetas_list, ensure_ascii=False) if recetas_list else '[]'

    return render_template(
        "catalogos/compartidos/quimicos_recetas.html",
        quimicos=quimicos,
        recetas=recetas,
        recetas_json_str=recetas_json_str
    )


@catalogos_bp.route("/catalogos/consumos")
@admin_required
def consumos():
    """Panel de gestión de Consumos"""
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
    return render_template("catalogos/compartidos/consumos.html", consumos=consumos)


# =========================
# REGULARES
# =========================

@catalogos_bp.route('/catalogos/regulares/elementos')
@admin_required
def elementos():
    """Página de gestión de elementos"""
    return render_template('catalogos/regulares/elementos.html')


@catalogos_bp.route("/catalogos/herramientas")
@admin_required
def herramientas():
    """Página de gestión de herramientas"""
    return render_template("catalogos/regulares/herramientas.html")


@catalogos_bp.route("/catalogos/kits")
@admin_required
def kits():
    """Página de gestión de kits"""
    return render_template("catalogos/regulares/kits.html")


@catalogos_bp.route("/catalogos/fracciones")
@admin_required
def fracciones():
    """Panel de gestión de Fracciones"""
    return render_template("catalogos/regulares/fracciones.html")


@catalogos_bp.route("/catalogos/fracciones/<fraccion_id>/metodologias")
@admin_required
def fraccion_metodologias(fraccion_id):
    """Página de configuración de metodologías de una fracción"""
    fraccion = Fraccion.query.get(fraccion_id)

    if not fraccion:
        flash(f"Fracción {fraccion_id} no encontrada", "error")
        return redirect(url_for('catalogos.fracciones'))

    return render_template(
        "catalogos/regulares/metodologias_fraccion.html",
        fraccion=fraccion
    )


# =========================
# EVENTOS
# =========================

@catalogos_bp.route("/catalogos/kits-eventos")
@admin_required
def kits_eventos():
    """Página de gestión de kits de eventos"""
    return render_template("catalogos/eventos/kits_eventos.html")


@catalogos_bp.route("/catalogos/fracciones-eventos")
@admin_required
def fracciones_eventos():
    """Página de gestión de fracciones de eventos"""
    return render_template("catalogos/eventos/fracciones_eventos.html")


@catalogos_bp.route("/catalogos/metodologias-eventos/<metodologia_id>")
@admin_required
def metodologia_evento_detalle(metodologia_id):
    """Página de edición de pasos de una metodología de evento"""
    metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)

    if not metodologia:
        flash(f"Metodología {metodologia_id} no encontrada", "error")
        return redirect(url_for('catalogos.fracciones_eventos'))

    fraccion = metodologia.fraccion
    evento = EventoCatalogo.query.get(fraccion.evento_tipo_id) if fraccion else None

    return render_template(
        "catalogos/eventos/metodologia_evento_detalle.html",
        metodologia=metodologia,
        fraccion=fraccion,
        evento=evento,
        hide_nav=True
    )
