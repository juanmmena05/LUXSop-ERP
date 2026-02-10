# routes_v2.py
import unicodedata
from typing import Optional
from datetime import datetime, date, timedelta, timezone

# =====================================================
# 📝 IMPORTS NECESARIOS (agregar al inicio de tu archivo)
# =====================================================
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, make_response, abort, session
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_
from sqlalchemy import func, distinct
from sqlalchemy.exc import IntegrityError

from flask_login import login_user, logout_user, login_required, current_user

from .models import User
from functools import wraps

from functools import lru_cache

import os
import pdfkit
import shutil

from .extensions import db
from .models import (
    # Core
    Area, SubArea, SOP, NivelLimpieza, Personal,

    # Catalogos / armado SOP
    Fraccion, Metodologia, MetodologiaBase, MetodologiaBasePaso,

    SopFraccion, SopFraccionDetalle,

    # Planeacion
    LanzamientoSemana, LanzamientoDia, LanzamientoTarea,
    AsignacionPersonal,
    PlantillaSemanal, PlantillaItem, PlantillaSemanaAplicada,
    TareaCheck,

    # Eventos y Tareas Especiales (NUEVO)
    EventoCatalogo, CasoCatalogo, SopEventoFraccion, 
    MetodologiaEventoFraccion, 
    MetodologiaEventoFraccionPaso,
    SopEvento, SopEventoDetalle,

    # Recursos / elementos
    Elemento, ElementoSet, ElementoDetalle,
    Kit, KitDetalle, Herramienta,
    Receta, RecetaDetalle, Quimico, Consumo,
)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

# =========================
# Helpers de PDF
# =========================
try:
    import pdfkit
except Exception:
    pdfkit = None

WKHTMLTOPDF_CMD = os.getenv("WKHTMLTOPDF_CMD") or shutil.which("wkhtmltopdf")

PDFKIT_CONFIG = None
if pdfkit and WKHTMLTOPDF_CMD:
    try:
        PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_CMD)
    except Exception:
        PDFKIT_CONFIG = None


PDF_OPTIONS = {
    "page-size": "A5",
    "encoding": "UTF-8",
    "margin-top": "6mm",
    "margin-bottom": "6mm",
    "margin-left": "6mm",
    "margin-right": "6mm",
    "zoom": "1.15",
}

# =========================
# Helpers semana/día
# =========================
def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())

def get_or_create_semana(fecha_obj: date):
    lunes = get_monday(fecha_obj)
    semana = LanzamientoSemana.query.filter_by(fecha_inicio=lunes).first()
    if not semana:
        semana = LanzamientoSemana(
            nombre=f"Semana {lunes.isocalendar()[1]}",
            fecha_inicio=lunes
        )
        db.session.add(semana)
        db.session.commit()
    return semana

def get_or_create_dia(fecha_obj: date):
    semana = get_or_create_semana(fecha_obj)
    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj, semana_id=semana.semana_id).first()
    if not dia:
        dia = LanzamientoDia(semana_id=semana.semana_id, fecha=fecha_obj)
        db.session.add(dia)
        db.session.commit()
    return dia


def crear_tareas_fijas(dia_id: int, personal_id: str):
    """Crea las 3 tareas fijas para un operario"""
    tareas_fijas = [
        {
            'tipo_tarea': 'inicio', 
            'orden': -3,
            'sop_evento_id': None,
            'es_arrastrable': False  # ✅ Nunca se mueve
        },
        {
            'tipo_tarea': 'receso', 
            'orden': 50,
            'sop_evento_id': None,
            'es_arrastrable': True  # ✅ Se puede mover
        },
        {
            'tipo_tarea': 'limpieza_equipo', 
            'orden': 999,
            'sop_evento_id': 'SP-LI-EQ-001',  # ✅ Evento configurado
            'es_arrastrable': False  # ✅ Siempre al final (o True si quieres permitir moverlo)
        }
    ]
    
    for tarea in tareas_fijas:
        t = LanzamientoTarea(
            dia_id=dia_id,
            personal_id=personal_id,
            tipo_tarea=tarea['tipo_tarea'],
            orden=tarea['orden'],
            sop_evento_id=tarea['sop_evento_id'],
            es_arrastrable=tarea['es_arrastrable']
        )
        db.session.add(t)
    
    db.session.commit()

def asegurar_tareas_fijas(dia_id: int, personal_id: str):
    """
    Verifica si un operario tiene tareas fijas en un día.
    Si NO las tiene, las crea automáticamente.
    """
    
    # ✅ Verificar con una sola query si ya tiene CUALQUIER tarea fija
    tiene_fijas = db.session.query(
        db.exists().where(
            db.and_(
                LanzamientoTarea.dia_id == dia_id,
                LanzamientoTarea.personal_id == personal_id,
                LanzamientoTarea.tipo_tarea.in_(['inicio', 'receso', 'limpieza_equipo'])
            )
        )
    ).scalar()
    
    if not tiene_fijas:
        crear_tareas_fijas(dia_id, personal_id)
        return True
    
    return False


# --- Helper: set etiqueta plantilla activa para una semana ---
def set_plantilla_activa(lunes: date, plantilla_id: int = None):
    """Marca o desmarca la plantilla activa de una semana"""
    marca = PlantillaSemanaAplicada.query.get(lunes)
    
    if plantilla_id is None:
        # Remover marca
        if marca:
            db.session.delete(marca)
    else:
        # Crear o actualizar marca
        if marca:
            marca.plantilla_id = plantilla_id
            marca.aplicada_en = datetime.now()  # ✅ Cambiar a "aplicada_en"
        else:
            marca = PlantillaSemanaAplicada(
                semana_lunes=lunes,  # ✅ Cambiar de "lunes" a "semana_lunes"
                plantilla_id=plantilla_id,
                aplicada_en=datetime.now()  # ✅ Cambiar de "fecha_aplicacion" a "aplicada_en"
            )
            db.session.add(marca)
    
    db.session.commit()

# =========================
# Helpers Nivel Limpieza (canon = "basica" | "media" | "profundo")
# =========================
def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s

def canon_nivel(s: Optional[str]) -> Optional[str]:
    x = _norm(s or "")
    if x in {"1", "basica", "básica"}:
        return "basica"
    if x in {"2", "media"}:
        return "media"
    if x in {"3", "profundo", "profunda"}:
        return "profundo"
    if x in {"4", "extraordinario", "extraordinaria"}:  # ✅ AÑADIR
        return "extraordinario"
    return None

def nivel_to_id(s: Optional[str]) -> Optional[int]:
    x = canon_nivel(s or "")
    return {
        "basica": 1, 
        "media": 2, 
        "profundo": 3,
        "extraordinario": 4  # ✅ AÑADIR
    }.get(x)

main_bp = Blueprint("main", __name__)


# =========================
# ====== HELPERS DE PLANTILLA ======
# =========================
def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())

def rango_lunes_a_sabado(lunes: date):
    return [lunes + timedelta(days=i) for i in range(6)]

def borrar_asignaciones_semana(lunes_destino: date):
    """Borra todas las tareas de la semana"""
    dias = [lunes_destino + timedelta(days=i) for i in range(6)]
    for d in dias:
        dia = LanzamientoDia.query.filter_by(fecha=d).first()
        if not dia:
            continue
        LanzamientoTarea.query.filter_by(dia_id=dia.dia_id).delete()
    db.session.commit()

def upsert_dia(fecha_obj: date) -> LanzamientoDia:
    return get_or_create_dia(fecha_obj)

def existe_tarea(fecha_obj: date, personal_id, subarea_id) -> bool:
    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return False
    return LanzamientoTarea.query.filter_by(
        dia_id=dia.dia_id,
        personal_id=personal_id,
        subarea_id=subarea_id
    ).first() is not None

def crear_tarea(fecha_obj: date, personal_id, area_id, subarea_id, nivel, orden=0):
    dia = upsert_dia(fecha_obj)
    t = LanzamientoTarea(
        dia_id=dia.dia_id,
        personal_id=personal_id,
        area_id=area_id,
        subarea_id=subarea_id,
        nivel_limpieza_asignado=canon_nivel(nivel) or "basica",
        orden=orden
    )
    db.session.add(t)
    
    # ✅ Crear tareas fijas si no existen
    asegurar_tareas_fijas(dia.dia_id, personal_id)

# ====== APLICADORES ======
def aplicar_ruta_base_personal(lunes_destino: date, overwrite: bool):
    if overwrite:
        borrar_asignaciones_semana(lunes_destino)

    base = AsignacionPersonal.query.all()
    dias = rango_lunes_a_sabado(lunes_destino)
    for fecha_obj in dias:
        for ap in base:
            if not existe_tarea(fecha_obj, ap.personal_id, ap.subarea_id):
                crear_tarea(fecha_obj, ap.personal_id, ap.area_id, ap.subarea_id, ap.nivel_limpieza_asignado)
    db.session.commit()

def aplicar_desde_semana(origen_lunes: date, destino_lunes: date, overwrite: bool):
    if overwrite:
        borrar_asignaciones_semana(destino_lunes)

    for i in range(6):
        fecha_origen = origen_lunes + timedelta(days=i)
        fecha_dest = destino_lunes + timedelta(days=i)
        dia_origen = LanzamientoDia.query.filter_by(fecha=fecha_origen).first()
        if not dia_origen:
            continue
        tareas = LanzamientoTarea.query.filter_by(dia_id=dia_origen.dia_id).all()
        for t in tareas:
            if not existe_tarea(fecha_dest, t.personal_id, t.subarea_id):
                crear_tarea(fecha_dest, t.personal_id, t.area_id, t.subarea_id, canon_nivel(t.nivel_limpieza_asignado) or "basica")
    db.session.commit()


def aplicar_plantilla_guardada(plantilla_id: int, destino_lunes: date, overwrite: bool):
    """Versión optimizada con bulk operations"""
    if overwrite:
        borrar_asignaciones_semana(destino_lunes)

    plantilla = PlantillaSemanal.query.options(
        db.joinedload(PlantillaSemanal.items)
    ).get_or_404(plantilla_id)
    
    if not plantilla.items:
        db.session.commit()
        return

    # ✅ 1. Pre-crear SEMANA y TODOS los días necesarios
    dias_map = {}  # {fecha: dia_id}
    fechas_necesarias = set()
    
    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        fechas_necesarias.add(fecha_dest)
    
    # Crear o buscar la semana
    semana = LanzamientoSemana.query.filter_by(fecha_inicio=destino_lunes).first()
    if not semana:
        semana = LanzamientoSemana(
            nombre=f"Semana {destino_lunes.isocalendar()[1]}",
            fecha_inicio=destino_lunes
        )
        db.session.add(semana)
        db.session.flush()  # Para obtener semana_id
    
    # Cargar días existentes
    dias_existentes = LanzamientoDia.query.filter(
        LanzamientoDia.fecha.in_(fechas_necesarias),
        LanzamientoDia.semana_id == semana.semana_id
    ).all()
    
    for dia in dias_existentes:
        dias_map[dia.fecha] = dia.dia_id
    
    # Crear días faltantes
    for fecha in fechas_necesarias:
        if fecha not in dias_map:
            nuevo_dia = LanzamientoDia(
                semana_id=semana.semana_id,
                fecha=fecha
            )
            db.session.add(nuevo_dia)
            db.session.flush()  # Para obtener el dia_id
            dias_map[fecha] = nuevo_dia.dia_id

    # ✅ 2. Pre-cargar tareas existentes para evitar duplicados
    dia_ids = list(dias_map.values())
    tareas_existentes = set()
    
    if dia_ids:
        tareas_actuales = db.session.query(
            LanzamientoTarea.dia_id,
            LanzamientoTarea.subarea_id,
            LanzamientoTarea.sop_id
        ).filter(
            LanzamientoTarea.dia_id.in_(dia_ids)
        ).all()
        
        for t in tareas_actuales:
            tareas_existentes.add((t.dia_id, t.subarea_id, t.sop_id))

    # ✅ 3. Pre-cargar SOPs para items viejos (sin sop_id)
    subareas_sin_sop = [it.subarea_id for it in plantilla.items if not getattr(it, 'sop_id', None)]
    sops_map = {}
    
    if subareas_sin_sop:
        sops = SOP.query.filter(
            SOP.subarea_id.in_(subareas_sin_sop),
            SOP.tipo_sop == "regular"
        ).all()
        for sop in sops:
            sops_map[sop.subarea_id] = sop.sop_id

    # ✅ 4. Trackear operarios únicos por día para tareas fijas
    operarios_por_dia = {}  # {dia_id: set(personal_ids)}

    # ✅ 5. Crear todas las tareas en batch
    tareas_a_insertar = []
    
    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        dia_id = dias_map[fecha_dest]
        
        # Obtener sop_id
        sop_id = getattr(it, 'sop_id', None)
        if not sop_id:
            sop_id = sops_map.get(it.subarea_id)
        
        es_adicional = getattr(it, 'es_adicional', False)
        
        # Verificar duplicados
        if not (es_adicional and sop_id and '-C' in sop_id):
            if (dia_id, it.subarea_id, sop_id) in tareas_existentes:
                continue
        
        # Crear tarea
        t = LanzamientoTarea(
            dia_id=dia_id,
            personal_id=it.personal_id,
            area_id=it.area_id,
            subarea_id=it.subarea_id,
            nivel_limpieza_asignado=canon_nivel(it.nivel_limpieza_asignado) or "basica",
            sop_id=sop_id,
            es_adicional=es_adicional,
            orden=it.orden or 0
        )
        tareas_a_insertar.append(t)
        
        # Registrar operario para tareas fijas
        if dia_id not in operarios_por_dia:
            operarios_por_dia[dia_id] = set()
        operarios_por_dia[dia_id].add(it.personal_id)
    
    # ✅ 6. Bulk insert de tareas
    if tareas_a_insertar:
        db.session.bulk_save_objects(tareas_a_insertar)
    
    # ✅ 7. Crear tareas fijas para operarios únicos (una sola vez por operario/día)
    for dia_id, personal_ids in operarios_por_dia.items():
        for personal_id in personal_ids:
            asegurar_tareas_fijas(dia_id, personal_id)
    
    db.session.commit()


# =========================
# Helpers Tablas HTML
# =========================
def na(x) -> str:
    return x if x and str(x).strip() else "No aplica"


def fmt_consumo(c) -> str:
    """
    Queremos: "3 disparos = 3 mL"
    (sin ID, sin pipes, sin paréntesis)
    """
    if not c:
        return "No aplica"

    v = getattr(c, "valor", None)          # ej: 3
    u = getattr(c, "unidad", None)         # ej: "disparos"
    regla = getattr(c, "regla", None)      # ej: "= 3 mL"  ó  "3 mL"

    left = None
    if v is not None and u:
        left = f"{v:g} {u}".strip()

    if regla:
        r = str(regla).strip()
        # normaliza para que quede "... = 3 mL"
        if not r.startswith("="):
            r = f"= {r}"
        return f"{left} {r}".strip() if left else r

    return left or "No aplica"


def fmt_herramientas(kit) -> list[str]:
    """
    Devuelve una lista de descripciones de herramientas.
    Si no hay herramientas, devuelve lista vacía.
    """
    if not kit:
        return []
    dets = getattr(kit, "detalles", None) or []
    return [
        kd.herramienta.descripcion
        for kd in dets
        if getattr(kd, "herramienta", None) and getattr(kd.herramienta, "descripcion", None)
    ]


def fmt_herramientas_list(kit) -> list[str]:
    items = fmt_herramientas(kit)  # lista real de herramientas
    return items if items else ["No aplica"]




def fmt_receta(receta) -> str:
    """
    Regresa solo: "8 mL + 1000 mL" (sin nombre, sin paréntesis).
    Si no hay detalles, regresa el nombre de la receta.
    """
    if not receta:
        return "No aplica"

    dets = getattr(receta, "detalles", None) or []
    if not dets:
        return na(getattr(receta, "nombre", None))

    partes = []
    for d in dets:
        # dosis
        if getattr(d, "dosis", None) is not None and getattr(d, "unidad_dosis", None):
            partes.append(f"{d.dosis:g} {d.unidad_dosis}".strip())

        # base
        if getattr(d, "volumen_base", None) is not None and getattr(d, "unidad_volumen", None):
            partes.append(f"{d.volumen_base:g} {d.unidad_volumen}".strip())

    # Caso común: ["8 mL", "1000 mL"] -> "8 mL + 1000 mL"
    s = " + ".join([p for p in partes if p])
    return s.strip() if s.strip() else na(getattr(receta, "nombre", None))


def fmt_quimico_y_receta(receta) -> tuple[str, str]:
    """
    Químico: "Alpha HP + ..."
    Receta:  SOLO "8 mL + 1000 mL" (sin nombre, sin paréntesis)
    """
    if not receta:
        return "No aplica", "No aplica"

    dets = getattr(receta, "detalles", None) or []
    if not dets:
        return "No aplica", na(getattr(receta, "nombre", None))

    quimicos = []
    for d in dets:
        q = getattr(d, "quimico", None)
        if q and getattr(q, "nombre", None):
            quimicos.append(q.nombre)

    quimico_str = " + ".join(dict.fromkeys(quimicos)) if quimicos else "No aplica"
    receta_str = fmt_receta(receta)  # ✅ aquí ya va SIN nombre

    return quimico_str, receta_str


# Cache que expira cada 5 minutos
_cache_timestamp = {}

def get_cached_or_query(cache_key, query_func, timeout_minutes=5):
    now = datetime.now()
    
    if cache_key in _cache_timestamp:
        cached_time, cached_data = _cache_timestamp[cache_key]
        if now - cached_time < timedelta(minutes=timeout_minutes):
            return cached_data
    
    # Query fresh data
    data = query_func()
    _cache_timestamp[cache_key] = (now, data)
    return data

# Uso:
def get_all_areas():
    return get_cached_or_query(
        'areas_list',
        lambda: Area.query.order_by(Area.orden_area).all(),
        timeout_minutes=10
    )


# =========================
# HOME (router)
# =========================
@main_bp.route("/")
@login_required
def home():
    # admin -> panel semanal
    if getattr(current_user, "role", None) == "admin":
        return redirect(url_for("main.home_admin_panel"))

    # operativo -> su ruta de hoy
    return redirect(url_for("main.mi_ruta"))



# =========================
# HOME ADMIN (panel semanal real)
# =========================
@main_bp.route("/admin")
@admin_required
def home_admin_panel():
    hoy = date.today()
    lunes = get_monday(hoy)
    _, semana_num, _ = lunes.isocalendar()
    dias_semana = []

    for offset in range(6):  # Lunes..Sábado
        fecha_dia = lunes + timedelta(days=offset)
        dia_db = LanzamientoDia.query.filter_by(fecha=fecha_dia).first()

        if dia_db:
            tareas = LanzamientoTarea.query.filter_by(dia_id=dia_db.dia_id).all()
            total_tareas = len(tareas)
            personas_unicas = {t.personal_id for t in tareas}
            total_personas = len(personas_unicas)
        else:
            total_tareas = 0
            total_personas = 0

        dias_semana.append({
            "fecha": fecha_dia,
            "total_tareas": total_tareas,
            "total_personas": total_personas,
            "link_ruta": url_for("main.ruta_dia", fecha=fecha_dia.strftime("%Y-%m-%d")),
            "link_plan": url_for("main.plan_dia_asignar", fecha=fecha_dia.strftime("%Y-%m-%d")),
        })

    sabado = lunes + timedelta(days=5)

    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    plantilla_activa = PlantillaSemanaAplicada.query.get(lunes)  # puede ser None

    return render_template(
        "home.html",
        dias_semana=dias_semana,
        lunes=lunes,
        sabado=sabado,
        semana_num=semana_num,
        plantillas=plantillas,
        plantilla_activa=plantilla_activa,
        hide_nav=False,  # opcional: si tu template usa esto
    )


# =========================
# ASIGNACIÓN RUTA BASE A PERSONAL
# =========================
@main_bp.route("/personal/<personal_id>/asignar", methods=["GET", "POST"])
@admin_required
def asignar_ruta(personal_id):
    persona = Personal.query.filter_by(personal_id=personal_id).first()
    areas = Area.query.all()
    subareas = SubArea.query.all()

    if request.method == "POST":
        area_id = request.form.get("area_id")
        subarea_id = request.form.get("subarea_id")
        nivel_limpieza_asignado = canon_nivel(request.form.get("nivel_limpieza_asignado"))
        if not nivel_limpieza_asignado:
            flash("Nivel de limpieza inválido.", "warning")
            return redirect(url_for("main.asignar_ruta", personal_id=personal_id))

        db.session.add(AsignacionPersonal(
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado,
        ))
        db.session.commit()
        return redirect(url_for("main.asignar_ruta", personal_id=personal_id))

    asignaciones = AsignacionPersonal.query.filter_by(personal_id=personal_id).all()
    return render_template(
        "asignacion_form.html",
        persona=persona, areas=areas, subareas=subareas, asignaciones=asignaciones
    )

# =========================
# BORRAR TAREA (día)
# =========================
@main_bp.route("/plan/<fecha>/borrar/<int:tarea_id>", methods=["POST"])
@admin_required
def borrar_tarea(fecha, tarea_id):
    try:
        tarea = LanzamientoTarea.query.get_or_404(tarea_id)
        
        # Eliminar check asociado
        check = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
        if check:
            db.session.delete(check)
        
        db.session.delete(tarea)
        db.session.commit()
        
        # Si es AJAX, retornar JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Tarea eliminada'})
        
        # Si no es AJAX, redirect tradicional
        flash("Tarea eliminada correctamente.", "success")
        return redirect(url_for("main.plan_dia_asignar", fecha=fecha))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f"Error al eliminar: {str(e)}", "danger")
        return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

# =========================
# AJAX: subáreas por área (pintar ocupadas)
# =========================
@main_bp.route("/subareas_por_area/<area_id>")
def subareas_por_area(area_id):
    fecha_str = request.args.get("fecha")
    if fecha_str:
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    else:
        fecha_obj = date.today()

    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    ocupadas = set()
    if dia:
        ocupadas = {
            t.subarea_id
            for t in LanzamientoTarea.query.filter_by(dia_id=dia.dia_id).all()
        }

    subareas = SubArea.query.filter_by(area_id=area_id).order_by(SubArea.orden_subarea.asc()).all()
    return jsonify([
        {"id": s.subarea_id, "nombre": s.subarea_nombre, "ocupada": s.subarea_id in ocupadas}
        for s in subareas
    ])

# =========================
# PLAN DIARIO (asignar)
# =========================
@main_bp.route("/plan/<fecha>/asignar", methods=["GET", "POST"])
@admin_required
def plan_dia_asignar(fecha):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    dia = get_or_create_dia(fecha_obj)

    personal_list = Personal.query.all()
    areas_list = Area.query.all()
    subareas_list = SubArea.query.order_by(SubArea.orden_subarea.asc()).all()

    if request.method == "POST":
        personal_id = request.form.get("personal_id")
        area_id = request.form.get("area_id")
        subarea_id = request.form.get("subarea_id")
        nivel_limpieza_asignado = canon_nivel(request.form.get("nivel_limpieza_asignado"))
        
        # Campos de los boxes
        es_adicional_str = request.form.get("es_adicional", "0")
        es_adicional = es_adicional_str == "1"
        tipo_sop_form = (request.form.get("tipo_sop") or "regular").strip().lower()
        
        # ✅ MAPEO: "extraordinario" en UI → "regular" en BD
        if tipo_sop_form == "extraordinario":
            tipo_sop = "regular"
            nivel_limpieza_asignado = "extraordinario"  # Forzar nivel
        elif tipo_sop_form == "consecuente":
            tipo_sop = "consecuente"
            nivel_limpieza_asignado = "basica"  # Forzar nivel
        else:
            tipo_sop = "regular"
        
        # Validar nivel
        if not nivel_limpieza_asignado:
            flash("Nivel de limpieza inválido.", "warning")
            return redirect(url_for("main.plan_dia_asignar", fecha=fecha))
        
        # ✅ VALIDACIÓN Box REGULAR: no permite subáreas ya asignadas como REGULAR (no adicional)
        if not es_adicional:
            existe_misma_subarea = LanzamientoTarea.query.filter_by(
                dia_id=dia.dia_id,
                subarea_id=subarea_id,
                es_adicional=False
            ).first()
            if existe_misma_subarea:
                flash("Esa subárea ya tiene una tarea REGULAR asignada en este día.", "warning")
                return redirect(url_for("main.plan_dia_asignar", fecha=fecha))
        
        # Verificar que existe el SOP del tipo
        sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()
        if not sop:
            tipo_nombre = "Regular" if tipo_sop == "regular" else "Consecuente"
            flash(f"No existe SOP {tipo_nombre} para esta subárea.", "warning")
            return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

        # ✅ VALIDACIÓN de duplicados según tipo
        if tipo_sop == "consecuente":
            # Consecuentes: ILIMITADAS - no validar duplicados
            pass
        else:
            # Regular (incluyendo extraordinario): solo 1 por sop_id
            existe_mismo_sop = LanzamientoTarea.query.filter_by(
                dia_id=dia.dia_id,
                subarea_id=subarea_id,
                sop_id=sop.sop_id
            ).first()
            if existe_mismo_sop:
                # Determinar si es extraordinario o regular normal
                if nivel_limpieza_asignado == "extraordinario":
                    flash(f"Ya existe una tarea Regular/Extraordinario para esta subárea.", "warning")
                else:
                    flash(f"Ya existe una tarea Regular para esta subárea en este día.", "warning")
                return redirect(url_for("main.plan_dia_asignar", fecha=fecha))
            
        # Crear tarea
        t = LanzamientoTarea(
            dia_id=dia.dia_id,
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado,
            sop_id=sop.sop_id,
            es_adicional=es_adicional,
            tipo_tarea='sop',  # ← Marcar explícitamente como SOP
            es_arrastrable=True  # ← SOPs son arrastrables
        )
        db.session.add(t)
        asegurar_tareas_fijas(dia.dia_id, personal_id)
        
        db.session.commit()
        
        return redirect(url_for("main.plan_dia_asignar", fecha=fecha))
    # ========== GET ========= (OPTIMIZADO)
    tareas_del_dia = (
        LanzamientoTarea.query
        .filter_by(dia_id=dia.dia_id)
        .options(
            # Cargar relaciones básicas
            joinedload(LanzamientoTarea.personal),
            joinedload(LanzamientoTarea.area),
            joinedload(LanzamientoTarea.subarea),
            # SOPs con fracciones y detalles
            joinedload(LanzamientoTarea.sop)
                .selectinload(SOP.sop_fracciones)
                .selectinload(SopFraccion.detalles),
            # Eventos con todos sus datos
            joinedload(LanzamientoTarea.sop_evento)
                .selectinload(SopEvento.detalles)
        )
        .all()
    )


    tiempos_por_tarea = {t.tarea_id: calcular_tiempo_tarea(t) for t in tareas_del_dia}

    # Separar tareas
    tareas_regulares = [t for t in tareas_del_dia if not getattr(t, 'es_adicional', False)]

    tareas_por_persona = {}
    for t in tareas_del_dia:
        key = t.personal_id
        if key not in tareas_por_persona:
            persona = getattr(t, "personal", None) or Personal.query.filter_by(personal_id=key).first()
            tareas_por_persona[key] = {"persona": persona, "subtareas": []}
        tareas_por_persona[key]["subtareas"].append(t)

    for key in tareas_por_persona:
        tareas_por_persona[key]["subtareas"].sort(key=lambda x: (
            x.orden or 0,
            x.area.orden_area if x.area else 0,
            x.subarea.orden_subarea if x.subarea else 0
        ))

    tiempo_total_por_persona = {}
    for persona_id, grupo in tareas_por_persona.items():
        total = sum(tiempos_por_tarea.get(t.tarea_id, 0) for t in grupo["subtareas"])
        tiempo_total_por_persona[persona_id] = round(total, 1)

    asignadas_regular_ids = {t.subarea_id for t in tareas_regulares}

    return render_template(
        "plan_dia_form.html",
        fecha=fecha_obj,
        personal_list=personal_list,
        areas_list=areas_list,
        subareas_list=subareas_list,
        tareas_del_dia=tareas_del_dia,
        tareas_por_persona=tareas_por_persona,
        tiempos_por_tarea=tiempos_por_tarea,
        tiempo_total_por_persona=tiempo_total_por_persona,
        asignadas_ids=asignadas_regular_ids,
        asignadas_regular_ids=asignadas_regular_ids,
        hide_nav=True,
    )



# =========================
# Calcular Tiempo Tarea (v2) - CORREGIDO
# =========================
def calcular_tiempo_tarea(tarea):
    """
    Calcula el tiempo estimado de una tarea según su tipo.
    
    OPTIMIZADO: No hace queries adicionales, usa relaciones ya cargadas.
    """
    
    # Tareas fijas con tiempos hardcoded
    if tarea.tipo_tarea == 'inicio':
        return 0
    elif tarea.tipo_tarea == 'receso':
        return 45
    elif tarea.tipo_tarea == 'limpieza_equipo':
        # Si tiene sop_evento, calcular tiempo real
        if tarea.sop_evento and tarea.sop_evento.detalles:
            return sum(detalle.tiempo_estimado for detalle in tarea.sop_evento.detalles)
        return 60  # Fallback
    
    # Eventos: calcular de las fracciones del SopEvento
    elif tarea.tipo_tarea == 'evento':
        if tarea.sop_evento and tarea.sop_evento.detalles:
            return sum(detalle.tiempo_estimado for detalle in tarea.sop_evento.detalles)
        return 0
    
    # SOPs regulares: calcular de las fracciones
    elif tarea.tipo_tarea == 'sop':
        if not tarea.sop or not tarea.nivel_limpieza_asignado:
            return 0
        
        # ✅ OPTIMIZACIÓN: Usar tarea.sop en vez de query.get()
        sop = tarea.sop
        
        nivel_id = nivel_to_id(canon_nivel(tarea.nivel_limpieza_asignado))
        if not nivel_id:
            return 0
        
        tiempo_total = 0
        for sop_fraccion in sop.sop_fracciones or []:
            detalle = next(
                (d for d in (sop_fraccion.detalles or []) if d.nivel_limpieza_id == nivel_id),
                None
            )
            if detalle and detalle.tiempo_unitario_min:
                tiempo_total += float(detalle.tiempo_unitario_min)
        
        return tiempo_total
    
    # Tipo desconocido
    return 0


# =========================
# Ruta Día (centro de reportes)
# =========================
@main_bp.route("/plan/<fecha>/ruta")
@admin_required
def ruta_dia(fecha):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    personas = []

    if dia:
        tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id).all()
        vistos = set()
        for t in tareas:
            p = getattr(t, "personal", None) or Personal.query.filter_by(personal_id=t.personal_id).first()
            if p and p.personal_id not in vistos:
                personas.append(p)
                vistos.add(p.personal_id)

    return render_template("ruta_dia.html", fecha=fecha_obj, personas=personas, hide_nav=True)

# =========================
# REPORTE (micro) — HTML reporte_personal.html
# =========================
@main_bp.route("/reporte/<fecha>/<personal_id>")
@login_required
def reporte_persona_dia(fecha, personal_id):
    from sqlalchemy.orm import selectinload

    # Determinar si el usuario puede hacer checks
    puede_hacer_check = False
    es_hoy = (fecha == date.today().strftime("%Y-%m-%d"))

    if current_user.role != "admin":
        if current_user.personal_id != personal_id:
            abort(403)
        if not es_hoy:
            abort(403)
        puede_hacer_check = True

    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return f"No existe un registro de día para la fecha {fecha}.", 404

    # Cargar TODAS las tareas (SOPs + Fijas + Eventos) - OPTIMIZADO
    tareas = (
        LanzamientoTarea.query
        .filter_by(dia_id=dia.dia_id, personal_id=personal_id)
        .options(
            # Relaciones básicas (joinedload para 1:1)
            joinedload(LanzamientoTarea.personal),
            joinedload(LanzamientoTarea.area),
            joinedload(LanzamientoTarea.subarea),
            joinedload(LanzamientoTarea.sop),
            # Eventos (selectinload para 1:many para reducir cartesian product)
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.evento_catalogo),
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.caso_catalogo),
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.detalles).selectinload(SopEventoDetalle.fraccion).selectinload(SopEventoFraccion.metodologia).selectinload(MetodologiaEventoFraccion.pasos),
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.detalles).selectinload(SopEventoDetalle.kit).selectinload(Kit.detalles).selectinload(KitDetalle.herramienta),
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.detalles).selectinload(SopEventoDetalle.receta).selectinload(Receta.detalles).selectinload(RecetaDetalle.quimico),
            selectinload(LanzamientoTarea.sop_evento).selectinload(SopEvento.detalles).selectinload(SopEventoDetalle.consumo),


        )
        .order_by(LanzamientoTarea.orden, LanzamientoTarea.tarea_id)
        .all()
    )

    if not tareas:
        persona = Personal.query.filter_by(personal_id=personal_id).first()
        nombre = persona.nombre if persona else personal_id
        return f"No hay tareas para {nombre} el {fecha}.", 404

    # Obtener checks existentes
    tarea_ids = [t.tarea_id for t in tareas]
    checks_map = {}
    if tarea_ids:
        checks = TareaCheck.query.filter(TareaCheck.tarea_id.in_(tarea_ids)).all()
        checks_map = {c.tarea_id: c.checked_at.strftime("%H:%M") for c in checks}

    persona = tareas[0].personal

    # ===== SEPARAR TAREAS POR TIPO =====
    tareas_sop = [t for t in tareas if t.tipo_tarea == 'sop']
    tareas_fijas = [t for t in tareas if t.tipo_tarea in ('inicio', 'receso', 'limpieza_equipo')]
    tareas_evento = [t for t in tareas if t.tipo_tarea == 'evento']

    # ===== PROCESAR SOPs (código existente) =====
    sop_ids = list({t.sop_id for t in tareas_sop if t.sop_id})
    subarea_ids_sin_sop = list({t.subarea_id for t in tareas_sop if not t.sop_id and t.subarea_id})

    detalles = []

    # Solo procesar SOPs si existen
    if sop_ids or subarea_ids_sin_sop:
        query_filters = []
        if sop_ids:
            query_filters.append(SOP.sop_id.in_(sop_ids))
        if subarea_ids_sin_sop:
            query_filters.append(and_(SOP.subarea_id.in_(subarea_ids_sin_sop), SOP.tipo_sop == "regular"))

        sops_full = (
            SOP.query
            .filter(or_(*query_filters))
            .options(
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.fraccion),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.kit).selectinload(Kit.detalles).selectinload(KitDetalle.herramienta),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.receta).selectinload(Receta.detalles).selectinload(RecetaDetalle.quimico),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.consumo),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.elemento_set).selectinload(ElementoSet.detalles).selectinload(ElementoDetalle.elemento),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.elemento_set).selectinload(ElementoSet.detalles).selectinload(ElementoDetalle.receta).selectinload(Receta.detalles).selectinload(RecetaDetalle.quimico),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.elemento_set).selectinload(ElementoSet.detalles).selectinload(ElementoDetalle.kit).selectinload(Kit.detalles).selectinload(KitDetalle.herramienta),
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles).selectinload(SopFraccionDetalle.elemento_set).selectinload(ElementoSet.detalles).selectinload(ElementoDetalle.consumo),
            )
            .all()
        )

        sops_dict = {sop.sop_id: sop for sop in sops_full}
        sops_por_subarea = {sop.subarea_id: sop for sop in sops_full if sop.tipo_sop == "regular"}

        all_fraccion_ids = set()
        all_nivel_ids = set()

        for t in tareas_sop:
            nivel_id = nivel_to_id(canon_nivel(t.nivel_limpieza_asignado))
            if nivel_id:
                all_nivel_ids.add(nivel_id)

        for sop in sops_full:
            for sf in sop.sop_fracciones or []:
                all_fraccion_ids.add(sf.fraccion_id)

        met_map = build_met_map(all_fraccion_ids, all_nivel_ids)

        # Procesar SOPs (código existente)
        for t in tareas_sop:
            area = t.area
            subarea = t.subarea
            if not area or not subarea:
                continue

            sop_id = t.sop_id
            sop_full = sops_dict.get(sop_id) if sop_id else None

            if not sop_full and subarea:
                sop_full = sops_por_subarea.get(subarea.subarea_id)
                if sop_full:
                    sop_id = sop_full.sop_id

            if not sop_full:
                continue

            nivel_asignado = canon_nivel(t.nivel_limpieza_asignado)
            nivel_id = nivel_to_id(nivel_asignado)
            if not nivel_id:
                continue

            fracciones_filtradas = []
            tiempo_total_min = 0.0

            for sf in sop_full.sop_fracciones or []:
                sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == nivel_id), None)
                if not sd:
                    continue

                fr = sf.fraccion
                metodologia = met_map.get((sf.fraccion_id, sd.nivel_limpieza_id))
                if not metodologia:
                    continue

                receta = sd.receta
                kit = sd.kit
                elemento_set = sd.elemento_set
                consumo_sd = sd.consumo

                tiempo_min = float(sd.tiempo_unitario_min) if sd.tiempo_unitario_min is not None else None
                if tiempo_min is not None:
                    tiempo_total_min += tiempo_min

                tabla = None

                if elemento_set:
                    headers = ["Elemento", "Cantidad", "Químico", "Receta", "Consumo", "Herramienta"]
                    rows = []

                    for ed in sorted((elemento_set.detalles or []), key=lambda x: (x.orden or 9999, x.elemento_id)):
                        elemento = ed.elemento
                        q_str, r_str = fmt_quimico_y_receta(ed.receta)
                        c_str = fmt_consumo(ed.consumo)
                        h_str = fmt_herramientas_list(ed.kit)

                        rows.append([
                            na(elemento.descripcion if elemento else None),
                            na(str(elemento.cantidad if elemento else "")),
                            q_str,
                            r_str,
                            c_str,
                            h_str,
                        ])

                    tabla = {"headers": headers, "rows": rows}
                else:
                    headers = ["Químico", "Receta", "Consumo", "Herramienta"]
                    q_str, r_str = fmt_quimico_y_receta(receta)
                    c_str = fmt_consumo(consumo_sd)
                    h_str = fmt_herramientas_list(kit)
                    tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}

                fracciones_filtradas.append({
                    "orden": sf.orden,
                    "fraccion_nombre": fr.fraccion_nombre if fr else "",
                    "nombre_full": fr.nombre_full if fr else "",
                    "descripcion": metodologia.descripcion or "",
                    "nivel_limpieza": nivel_asignado,
                    "tiempo_min": round(tiempo_min, 2) if tiempo_min is not None else None,
                    "metodologia": metodologia,
                    "tabla": tabla,
                    "observacion_critica": (fr.nota_tecnica if fr else None),
                })

            detalles.append({
                "tarea_id": t.tarea_id,
                "tipo_tarea": "sop",
                "area": area.area_nombre,
                "subarea": subarea.subarea_nombre,
                "nivel": nivel_asignado,
                "tiempo_total_min": round(tiempo_total_min, 2),
                "observacion_critica": sop_full.observacion_critica_sop,
                "fracciones": fracciones_filtradas,
                "orden": t.orden if t.orden is not None else 0,
                "orden_area": area.orden_area if area.orden_area is not None else 9999,
                "orden_subarea": subarea.orden_subarea if subarea.orden_subarea is not None else 9999,
                "es_adicional": t.es_adicional if hasattr(t, 'es_adicional') else False,
                "sop_id": sop_id,
            })
    # ===== PROCESAR TAREAS FIJAS (CORREGIDO) =====
    for t in tareas_fijas:
        tipo_nombre = {
            'inicio': 'INICIO',
            'receso': 'RECESO',
            'limpieza_equipo': 'LIMPIEZA DE EQUIPO'
        }.get(t.tipo_tarea, t.tipo_tarea.upper())

        # Si la tarea fija tiene sop_evento_id (caso limpieza_equipo), procesarla como evento
        if t.sop_evento_id and t.sop_evento:
            sop_evento = t.sop_evento
            
            # Calcular tiempo total sumando fracciones
            tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
            
            # Construir fracciones para el reporte
            fracciones_evento = []
            for detalle in sop_evento.detalles:
                fraccion = detalle.fraccion
                metodologia = fraccion.metodologia if fraccion else None
                
                # Construir tabla de recursos (formato eventos: 4 columnas)
                tabla = None
                if detalle.kit or detalle.receta or detalle.consumo:
                    headers = ["Químico", "Receta", "Consumo", "Herramienta"]
                    q_str, r_str = fmt_quimico_y_receta(detalle.receta)
                    c_str = fmt_consumo(detalle.consumo)
                    h_str = fmt_herramientas_list(detalle.kit)
                    tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}
                
                fracciones_evento.append({
                    "orden": detalle.orden,
                    "fraccion_nombre": fraccion.nombre if fraccion else "",
                    "nombre_full": fraccion.nombre if fraccion else "",  # ✅ AGREGADO
                    "descripcion": metodologia.descripcion if metodologia else "",
                    "nivel_limpieza": "—",
                    "tiempo_min": detalle.tiempo_estimado,
                    "metodologia": metodologia,
                    "tabla": tabla,
                    "observacion_critica": detalle.observaciones,
                })
            
            detalles.append({
                "tarea_id": t.tarea_id,
                "tipo_tarea": t.tipo_tarea,
                "area": "—",
                "subarea": tipo_nombre,
                "nivel": "—",
                "tiempo_total_min": tiempo_total,
                "observacion_critica": sop_evento.descripcion,
                "fracciones": fracciones_evento,
                "orden": t.orden if t.orden is not None else 0,
                "orden_area": 0,
                "orden_subarea": 0,
                "es_adicional": False,
                "sop_id": None,
            })
        else:
            # Tareas fijas sin sop_evento_id (inicio, receso)
            tiempo_fijo = {
                'receso': 45,
                'limpieza_equipo': 60  # fallback si no hay sop_evento_id
            }.get(t.tipo_tarea, 0)

            detalles.append({
                "tarea_id": t.tarea_id,
                "tipo_tarea": t.tipo_tarea,
                "area": "—",
                "subarea": tipo_nombre,
                "nivel": "—",
                "tiempo_total_min": tiempo_fijo,
                "observacion_critica": None,
                "fracciones": [],
                "orden": t.orden if t.orden is not None else 0,
                "orden_area": 0,
                "orden_subarea": 0,
                "es_adicional": False,
                "sop_id": None,
            })


    # ===== PROCESAR EVENTOS (CORREGIDO) =====
    for t in tareas_evento:
        sop_evento = t.sop_evento
        if not sop_evento:
            continue
        
        caso_nombre = sop_evento.caso_catalogo.nombre
        evento_nombre = sop_evento.evento_catalogo.nombre
        area_nombre = t.area.area_nombre if t.area else "Sin área"
        
        # Calcular tiempo total sumando fracciones
        tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
        
        # Construir fracciones para el reporte
        fracciones_evento = []
        for detalle in sop_evento.detalles:
            fraccion = detalle.fraccion
            metodologia = fraccion.metodologia if fraccion else None
            
            # Construir tabla de recursos (formato eventos: 4 columnas)
            tabla = None
            if detalle.kit or detalle.receta or detalle.consumo:
                headers = ["Químico", "Receta", "Consumo", "Herramienta"]
                q_str, r_str = fmt_quimico_y_receta(detalle.receta)
                c_str = fmt_consumo(detalle.consumo)
                h_str = fmt_herramientas_list(detalle.kit)
                tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}
            
            fracciones_evento.append({
                "orden": detalle.orden,
                "fraccion_nombre": fraccion.nombre if fraccion else "",
                "nombre_full": fraccion.nombre if fraccion else "",  # ✅ AGREGADO
                "descripcion": metodologia.descripcion if metodologia else "",
                "nivel_limpieza": "—",
                "tiempo_min": detalle.tiempo_estimado,
                "metodologia": metodologia,
                "tabla": tabla,
                "observacion_critica": detalle.observaciones,
            })
        
        detalles.append({
            "tarea_id": t.tarea_id,
            "tipo_tarea": "evento",
            "area": area_nombre,
            "subarea": f"EVENTO: {evento_nombre} - {caso_nombre}",
            "nivel": "—",
            "tiempo_total_min": tiempo_total,
            "observacion_critica": sop_evento.descripcion,
            "fracciones": fracciones_evento,
            "orden": t.orden if t.orden is not None else 0,
            "orden_area": t.area.orden_area if t.area and t.area.orden_area is not None else 9999,
            "orden_subarea": t.subarea.orden_subarea if t.subarea and t.subarea.orden_subarea is not None else 9999,
            "es_adicional": False,
            "sop_id": None,
        })

    # Ordenar todos los detalles
    detalles.sort(key=lambda d: (d.get("orden", 0), d.get("orden_area", 9999), d.get("orden_subarea", 9999)))

    # Calcular progreso
    total_tareas = len(detalles)
    completadas = len([d for d in detalles if d["tarea_id"] in checks_map])
    progreso_pct = round((completadas / total_tareas * 100) if total_tareas > 0 else 0)

    return render_template(
        "reporte_personal.html",
        persona=persona,
        fecha=fecha_obj,
        detalles=detalles,
        checks_map=checks_map,
        puede_hacer_check=puede_hacer_check,
        total_tareas=total_tareas,
        completadas=completadas,
        progreso_pct=progreso_pct,
        hide_nav=True
    )


# =========================
# REPORTE Persona PDF (macro) — sop_macro_pdf.html
# =========================
@main_bp.route("/reporte/<fecha>/<personal_id>/pdf")
@login_required
def reporte_persona_dia_pdf(fecha, personal_id):
    # ✅ Opción 1: si PDF no está disponible (wkhtmltopdf), no romper app
    if (pdfkit is None) or (PDFKIT_CONFIG is None):
        flash("PDF no disponible en este servidor (wkhtmltopdf no está instalado o no se detectó).", "warning")
        return redirect(url_for("main.mi_ruta"))

    # Seguridad: operativo solo puede ver SU PDF y SOLO el de hoy
    if current_user.role != "admin":
        if current_user.personal_id != personal_id:
            abort(403)
        if fecha != date.today().strftime("%Y-%m-%d"):
            abort(403)

    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return f"Fecha inválida: {fecha}. Formato esperado: YYYY-MM-DD", 400

    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return f"No existe un registro de día para la fecha {fecha}.", 404

    tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id, personal_id=personal_id).all()
    if not tareas:
        persona = Personal.query.filter_by(personal_id=personal_id).first()
        nombre = persona.nombre if persona else personal_id
        return f"No hay tareas para {nombre} el {fecha}.", 404

    persona = getattr(tareas[0], "personal", None) or Personal.query.filter_by(personal_id=personal_id).first()
    detalles = []

    for t in tareas:
        area = t.area
        subarea = t.subarea
        if not area or not subarea:
            continue

        sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first()
        if not sop:
            continue

        nivel_asignado = canon_nivel(t.nivel_limpieza_asignado)
        nivel_id = nivel_to_id(nivel_asignado)
        if not nivel_id:
            continue

        sop_full = (
            SOP.query.options(
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.fraccion),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.consumo),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.elemento),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.consumo),
            )
            .filter_by(sop_id=sop.sop_id)
            .first()
        )
        if not sop_full:
            continue

        fraccion_ids = {sf.fraccion_id for sf in (sop_full.sop_fracciones or [])}
        met_map = build_met_map(fraccion_ids, {nivel_id})

        fracciones_filtradas = []
        tiempo_total_min = 0.0  # ✅ total por subárea

        for sf in (sop_full.sop_fracciones or []):
            sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == nivel_id), None)
            if not sd:
                continue

            fr = sf.fraccion
            metodologia = met_map.get((sf.fraccion_id, sd.nivel_limpieza_id))
            if not metodologia:
                continue

            pasos_items = sorted(list(metodologia.pasos or []), key=lambda p: (p.orden or 0))
            metodologia_dict = {
                "descripcion": metodologia.descripcion or "",
                "pasos": [{"instruccion": p.instruccion} for p in pasos_items]
            }

            receta = sd.receta
            kit = sd.kit
            elemento_set = sd.elemento_set
            consumo_sd = getattr(sd, "consumo", None)

            tiempo_min = float(sd.tiempo_unitario_min) if sd.tiempo_unitario_min is not None else None
            if tiempo_min is not None:
                tiempo_total_min += tiempo_min  # ✅ suma

            if elemento_set:
                headers = ["Elemento", "Cantidad", "Químico", "Receta", "Consumo", "Herramienta"]
                rows = []
                for ed in sorted((elemento_set.detalles or []), key=lambda x: (x.orden or 9999, x.elemento_id)):
                    elemento = getattr(ed, "elemento", None)
                    q_str, r_str = fmt_quimico_y_receta(getattr(ed, "receta", None))
                    c_str = fmt_consumo(getattr(ed, "consumo", None))
                    h_str = fmt_herramientas_list(getattr(ed, "kit", None))
                    rows.append([
                        na(getattr(elemento, "descripcion", None)),
                        na(str(getattr(elemento, "cantidad", None) or "")),
                        q_str,
                        r_str,
                        c_str,
                        h_str,
                    ])
                tabla = {"headers": headers, "rows": rows}
            else:
                headers = ["Químico", "Receta", "Consumo", "Herramienta"]
                q_str, r_str = fmt_quimico_y_receta(receta)
                c_str = fmt_consumo(consumo_sd)
                h_str = fmt_herramientas_list(kit)
                tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}

            fracciones_filtradas.append({
                "orden": sf.orden,
                "fraccion_nombre": fr.fraccion_nombre if fr else "",
                "nombre_full": fr.nombre_full if fr else "",
                "descripcion": metodologia.descripcion or "",
                "nivel_limpieza": nivel_asignado,
                "tiempo_base": round(tiempo_min, 2) if tiempo_min is not None else None,
                "tabla": tabla,
                "nota_tecnica": (fr.nota_tecnica if fr else None),
                "observacion_critica": sop.observacion_critica_sop,
                "metodologia": metodologia_dict,
            })

        detalles.append({
            "tarea_id": t.tarea_id,
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,

            # ✅ SOLO TIEMPO TOTAL EN MINUTOS (sin sop_id)
            "tiempo_total_min": round(tiempo_total_min, 2),

            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas,

            # ✅ claves de orden (SIN queries)
            "orden": t.orden if t.orden is not None else 0,
            "orden_area": area.orden_area if area.orden_area is not None else 9999,
            "orden_subarea": subarea.orden_subarea if subarea.orden_subarea is not None else 9999
        })

    
    if not detalles:
        return f"No fue posible generar el PDF para {personal_id} en {fecha} (sin detalles).", 404

    # ✅ sort correcto
    detalles.sort(key=lambda d: (d.get("orden", 0), d.get("orden_area", 9999), d.get("orden_subarea", 9999)))

    html = render_template("sop_macro_pdf.html", persona=persona, fecha=fecha_obj, detalles=detalles)

    options = PDF_OPTIONS if "PDF_OPTIONS" in globals() and isinstance(PDF_OPTIONS, dict) else {}

    try:
        pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=options)
    except Exception as e:
        flash(f"No se pudo generar el PDF: {e}", "warning")
        return redirect(url_for("main.mi_ruta"))

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename=SOP_{personal_id}_{fecha}.pdf"
    return resp


# =========================
# GUARDAR semana visible como plantilla (home.html)
# =========================
@main_bp.route("/plantillas/guardar_simple", methods=["POST"])
@admin_required
def guardar_semana_como_plantilla_simple():
    lunes_ref_str = request.form.get("lunes_ref")
    if not lunes_ref_str:
        return "Falta lunes_ref", 400
    lunes_ref = datetime.strptime(lunes_ref_str, "%Y-%m-%d").date()

    overwrite_flag = request.form.get("overwrite_template") == "on"
    plantilla_id_str = request.form.get("plantilla_id_to_overwrite")
    nombre = request.form.get("nombre")

    # Caso A: sobrescribir plantilla existente
    if overwrite_flag:
        if not plantilla_id_str:
            flash("Selecciona la plantilla a sobrescribir.", "warning")
            return redirect(url_for("main.home"))

        plantilla_id = int(plantilla_id_str)
        plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

        PlantillaItem.query.filter_by(plantilla_id=plantilla.plantilla_id).delete()

        for i in range(6):
            fecha_d = lunes_ref + timedelta(days=i)
            dia = LanzamientoDia.query.filter_by(fecha=fecha_d).first()
            if not dia:
                continue
            tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id).all()
            for t in tareas:
                db.session.add(PlantillaItem(
                    plantilla_id=plantilla.plantilla_id,
                    dia_index=i,
                    personal_id=t.personal_id,
                    area_id=t.area_id,
                    subarea_id=t.subarea_id,
                    nivel_limpieza_asignado=canon_nivel(t.nivel_limpieza_asignado) or "basica"
                ))

        db.session.commit()
        flash(f'Plantilla "{plantilla.nombre}" sobrescrita con la semana actual.', "success")
        return redirect(url_for("main.home"))

    # Caso B: crear nueva plantilla
    if not nombre:
        flash("Escribe un nombre para la nueva plantilla.", "warning")
        return redirect(url_for("main.home"))

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("main.home"))

    plantilla = PlantillaSemanal(nombre=nombre)
    db.session.add(plantilla)
    db.session.commit()

    for i in range(6):
        fecha_d = lunes_ref + timedelta(days=i)
        dia = LanzamientoDia.query.filter_by(fecha=fecha_d).first()
        if not dia:
            continue
        tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id).all()
        for t in tareas:
            db.session.add(PlantillaItem(
                plantilla_id=plantilla.plantilla_id,
                dia_index=i,
                personal_id=t.personal_id,
                area_id=t.area_id,
                subarea_id=t.subarea_id,
                nivel_limpieza_asignado=canon_nivel(t.nivel_limpieza_asignado) or "basica"
            ))

    db.session.commit()
    flash(f'Plantilla "{plantilla.nombre}" creada correctamente.', "success")
    return redirect(url_for("main.home"))

# =========================
# APLICAR plantilla guardada (home.html)
# =========================
@main_bp.route("/plantillas/aplicar_simple", methods=["POST"])
@admin_required
def aplicar_plantilla_guardada_simple():
    """Aplica plantilla con confirmación"""
    lunes_destino_str = request.form.get("lunes_destino")
    plantilla_id_str = request.form.get("plantilla_id")
    confirmar = request.form.get("confirmar", type=int, default=0)

    if not lunes_destino_str or not plantilla_id_str:
        flash("Faltan datos", "warning")
        return redirect(url_for("main.home_admin_panel"))

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()
    plantilla_id = int(plantilla_id_str)
    
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    plantilla_activa = PlantillaSemanaAplicada.query.get(lunes_destino)

    # Si no ha confirmado, mostrar modal
    if not confirmar:
        # Determinar tipo de confirmación
        if plantilla_activa and plantilla_activa.plantilla:
            # Caso 2: Cambio de plantilla
            mensaje = f"¿Estás seguro de cambiar a <strong>{plantilla.nombre}</strong>?"
            detalle = "Esto borrará todas las tareas actuales y aplicará la nueva plantilla desde cero."
        else:
            # Caso 1: Primera plantilla
            mensaje = f"¿Estás seguro de aplicar la plantilla <strong>{plantilla.nombre}</strong>?"
            detalle = f"Se agregarán las tareas programadas a la semana."
        
        return render_template(
            "confirmacion_modal.html",
            titulo="Confirmar Aplicación",
            mensaje=mensaje,
            detalle=detalle,
            form_action=url_for("main.aplicar_plantilla_guardada_simple"),
            form_data={
                "lunes_destino": lunes_destino_str,
                "plantilla_id": plantilla_id,
                "confirmar": 1
            },
            cancelar_url=url_for("main.home_admin_panel")
        )

    # Confirmado: aplicar plantilla
    borrar_asignaciones_semana(lunes_destino)
    aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite=False)
    set_plantilla_activa(lunes_destino, plantilla_id)

    flash(f"Plantilla '{plantilla.nombre}' aplicada correctamente.", "success")
    return redirect(url_for("main.home_admin_panel"))



@main_bp.route("/plantillas/borrar/<int:plantilla_id>", methods=["POST"])
@admin_required
def borrar_plantilla(plantilla_id):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    PlantillaItem.query.filter_by(plantilla_id=plantilla_id).delete()
    db.session.delete(plantilla)
    db.session.commit()
    flash(f'Plantilla "{plantilla.nombre}" eliminada correctamente.', "success")
    return redirect(url_for("main.home"))


# =========================
# SOP · Editor completo ElementoSet (selección + orden + kit/receta/consumo)
# =========================
@main_bp.route("/sop/<sop_id>/elementoset", methods=["GET", "POST"])
@admin_required
def sop_elementoset_edit(sop_id):

    tipo_sop = (request.args.get("tipo_sop") or request.form.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    # nivel por query o form
    nivel = (request.args.get("nivel") or request.form.get("nivel") or "").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    nivel_obj = NivelLimpieza.query.filter_by(nombre=nivel).first()
    if not nivel_obj:
        flash("Nivel de limpieza inválido.", "error")
        return redirect(url_for("main.sop_panel"))

    nivel_id = int(nivel_obj.nivel_limpieza_id)

    sop = SOP.query.filter_by(sop_id=sop_id).first_or_404()
    subarea = sop.subarea

    sop_fraccion_id = (request.args.get("sop_fraccion_id") or request.form.get("sop_fraccion_id") or "").strip()
    if not sop_fraccion_id:
        flash("Falta sop_fraccion_id.", "warning")
        return redirect(url_for("main.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop)) 

    sf = SopFraccion.query.filter_by(sop_fraccion_id=sop_fraccion_id, sop_id=sop_id).first()
    if not sf:
        abort(404)

    fr = sf.fraccion

    # Asegurar SopFraccionDetalle
    detalle = (
        SopFraccionDetalle.query
        .filter_by(sop_fraccion_id=sf.sop_fraccion_id, nivel_limpieza_id=nivel_id)
        .first()
    )
    if not detalle:
        detalle = SopFraccionDetalle(
            sop_fraccion_detalle_id=make_sd_id(sop.sop_id, fr.fraccion_id, nivel_id),
            sop_fraccion_id=sf.sop_fraccion_id,
            nivel_limpieza_id=nivel_id,
        )
        db.session.add(detalle)
        db.session.flush()

    # Asegurar ElementoSet único por (subarea, fraccion, nivel)
    es = None
    if detalle.elemento_set_id:
        es = ElementoSet.query.filter_by(elemento_set_id=detalle.elemento_set_id).first()

   
    if not es:
        # Buscar por ID esperado para este SOP específico
        es_id_expected = make_es_id(sop.sop_id, fr.fraccion_id, nivel_id)
        es = ElementoSet.query.filter_by(elemento_set_id=es_id_expected).first()

        if not es:
            es = ElementoSet(
                elemento_set_id=es_id_expected,
                subarea_id=subarea.subarea_id,
                fraccion_id=fr.fraccion_id,
                nivel_limpieza_id=nivel_id,
                nombre=f"{subarea.subarea_nombre} · {fr.fraccion_nombre} ({nivel})"
            )
            db.session.add(es)
            db.session.flush()

        detalle.elemento_set_id = es.elemento_set_id
        # regla: si hay elementos, limpio directos
        detalle.kit_id = None
        detalle.receta_id = None
        detalle.consumo_id = None
        db.session.commit()

    # ===== Elementos disponibles (por subárea) =====
    # OJO: si tu modelo Elemento NO tiene subarea_id, cambia este filtro a Elemento.query.all()
    elementos = (
        Elemento.query
        .filter_by(subarea_id=subarea.subarea_id)
        .order_by(Elemento.elemento_id.asc())
        .all()
    )

    # Detalles actuales del set
    detalles = (
        ElementoDetalle.query
        .filter_by(elemento_set_id=es.elemento_set_id)
        .all()
    )
    det_by_el = {d.elemento_id: d for d in (detalles or [])}

    # Catálogos
    recetas = Receta.query.order_by(Receta.nombre.asc()).all()
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
    kits = (
        Kit.query
        .filter(
            Kit.fraccion_id == fr.fraccion_id,
            or_(Kit.nivel_limpieza_id == None, Kit.nivel_limpieza_id == nivel_id)
        )
        .order_by(Kit.nombre.asc())
        .all()
    )

    # ===== POST: upsert + delete =====
    if request.method == "POST":
        selected_ids = request.form.getlist("elemento_id")
        selected_set = set(selected_ids)

        # borrar los que ya no están marcados
        for d in list(detalles or []):
            if str(d.elemento_id) not in selected_set:
                db.session.delete(d)

        # upsert marcados
        for el_id in selected_ids:
            orden_raw = (request.form.get(f"orden_{el_id}") or "").strip()
            orden = int(orden_raw) if orden_raw.isdigit() else None

            kit_id = (request.form.get(f"kit_{el_id}") or "").strip() or None
            receta_id = (request.form.get(f"receta_{el_id}") or "").strip() or None
            consumo_id = (request.form.get(f"consumo_{el_id}") or "").strip() or None

            d = det_by_el.get(el_id)
            if not d:
                d = ElementoDetalle(
                    elemento_set_id=es.elemento_set_id,
                    elemento_id=el_id,
                )
                db.session.add(d)

            d.orden = orden
            d.kit_id = kit_id
            d.receta_id = receta_id
            d.consumo_id = consumo_id

        db.session.commit()
        flash("✅ Elementos del set guardados.", "success")
        return redirect(url_for("main.sop_elementoset_edit", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf.sop_fraccion_id))

    return render_template(
        "sop_elementoset.html",
        sop=sop,
        subarea=subarea,
        nivel=nivel,
        nivel_id=nivel_id,
        nivel_obj=nivel_obj,
        sf=sf,
        fr=fr,
        es=es,
        elementos=elementos,
        det_by_el=det_by_el,
        kits=kits,
        recetas=recetas,
        consumos=consumos,
        tipo_sop=tipo_sop,
    )




# =========================
# Obtiene la Metodologia por Fraccion y Nivel Limpieza
# =========================
def build_met_map(fraccion_ids: set[str], nivel_ids: set[int]):
    """
    Regresa dict {(fraccion_id, nivel_id): MetodologiaBase} con pasos precargados.
    """
    if not fraccion_ids or not nivel_ids:
        return {}

    asignaciones = (
        Metodologia.query.options(
            joinedload(Metodologia.metodologia_base)
                .joinedload(MetodologiaBase.pasos)
        )
        .filter(
            Metodologia.fraccion_id.in_(list(fraccion_ids)),
            Metodologia.nivel_limpieza_id.in_(list(nivel_ids)),
        )
        .all()
    )

    # map: (fraccion_id, nivel_id) -> MetodologiaBase
    return {
        (m.fraccion_id, m.nivel_limpieza_id): m.metodologia_base
        for m in asignaciones
        if m.metodologia_base is not None
    }



# =========================
# Panel de Plantillas
# =========================
@main_bp.route("/plantillas")
@admin_required
def plantillas_panel():

    if current_user.role != "admin":
        abort(403)

    hoy = date.today()
    lunes_ref = get_monday(hoy)

    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()

    plantilla = None
    plantilla_id_str = request.args.get("plantilla_id", "").strip()
    if plantilla_id_str.isdigit():
        plantilla_id = int(plantilla_id_str)
        plantilla = (
            PlantillaSemanal.query.options(
                joinedload(PlantillaSemanal.items).joinedload(PlantillaItem.personal),
                joinedload(PlantillaSemanal.items).joinedload(PlantillaItem.subarea),
                joinedload(PlantillaSemanal.items).joinedload(PlantillaItem.area),
            )
            .filter_by(plantilla_id=plantilla_id)
            .first()
        )

    day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dias = [{"index": i, "nombre": day_names[i], "items": []} for i in range(6)]

    if plantilla:
        # agrupar items por dia_index
        for it in (plantilla.items or []):
            if it.dia_index is None:
                continue
            if 0 <= int(it.dia_index) <= 5:
                dias[int(it.dia_index)]["items"].append(it)

        # orden amigable dentro del día
        for d in dias:
            d["items"].sort(key=lambda x: (x.personal_id or "", x.area_id or "", x.subarea_id or ""))

    return render_template(
        "plantillas_panel.html",
        plantillas=plantillas,
        plantilla=plantilla,
        dias=dias,
        lunes_ref=lunes_ref.strftime("%Y-%m-%d"),
    )

# =========================
# REMOVER plantilla activa
# =========================
@main_bp.route("/plantillas/vaciar_semana", methods=["POST"])
@admin_required
def vaciar_semana():
    """Borra todas las tareas de la semana"""
    lunes_destino_str = request.form.get("lunes_destino")
    confirmar = request.form.get("confirmar", type=int, default=0)

    if not lunes_destino_str:
        flash("Falta fecha", "warning")
        return redirect(url_for("main.home_admin_panel"))

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()

    # Si no ha confirmado, mostrar modal
    if not confirmar:
        return render_template(
            "confirmacion_modal.html",
            titulo="Confirmar Vaciado",
            mensaje="¿Estás seguro de vaciar la semana?",
            detalle="Esto borrará todas las tareas y desactivará la plantilla.",
            form_action=url_for("main.vaciar_semana"),
            form_data={
                "lunes_destino": lunes_destino_str,
                "confirmar": 1
            },
            cancelar_url=url_for("main.home_admin_panel")
        )

    # Confirmado: vaciar todo
    borrar_asignaciones_semana(lunes_destino)
    set_plantilla_activa(lunes_destino, None)

    flash("Semana vaciada. Plantilla desactivada.", "success")
    return redirect(url_for("main.home_admin_panel"))

# =========================
# Crear plantilla vacía (desde cero)
# =========================
@main_bp.route("/plantillas/crear", methods=["POST"])
@admin_required
def plantillas_crear():
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        flash("Escribe un nombre para la plantilla.", "warning")
        return redirect(url_for("main.plantillas_panel"))

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("main.plantillas_panel"))

    plantilla = PlantillaSemanal(nombre=nombre)
    db.session.add(plantilla)
    db.session.commit()

    flash(f'Plantilla "{plantilla.nombre}" creada. Ahora puedes llenarla.', "success")
    return redirect(url_for("main.plantillas_panel", plantilla_id=plantilla.plantilla_id))


# =========================
# Agregar item a un día de una plantilla
# =========================
@main_bp.route("/plantillas/<int:plantilla_id>/item/add", methods=["POST"])
@admin_required
def plantilla_item_add(plantilla_id: int):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

    dia_index = request.form.get("dia_index")
    personal_id = request.form.get("personal_id")
    area_id = request.form.get("area_id")
    subarea_id = request.form.get("subarea_id")
    
    # ✅ NUEVOS CAMPOS
    es_adicional_str = request.form.get("es_adicional", "0")
    es_adicional = es_adicional_str == "1"
    tipo_sop_form = (request.form.get("tipo_sop") or "regular").strip().lower()
    nivel = canon_nivel(request.form.get("nivel_limpieza_asignado")) or "basica"

    # Validar dia_index
    if dia_index is None or not str(dia_index).isdigit():
        flash("Día inválido.", "warning")
        return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=0))

    dia_index = int(dia_index)
    if dia_index < 0 or dia_index > 5:
        flash("Día inválido (0..5).", "warning")
        return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=0))

    if not (personal_id and area_id and subarea_id):
        flash("Faltan datos (personal/área/subárea).", "warning")
        return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    # ✅ MAPEO: "extraordinario" en UI → "regular" en BD
    if tipo_sop_form == "extraordinario":
        tipo_sop = "regular"
        nivel = "extraordinario"
    elif tipo_sop_form == "consecuente":
        tipo_sop = "consecuente"
        nivel = "basica"
    else:
        tipo_sop = "regular"

    # ✅ VALIDACIÓN: Box REGULAR no permite subáreas ya asignadas como REGULAR
    if not es_adicional:
        existe_misma_subarea = PlantillaItem.query.filter_by(
            plantilla_id=plantilla_id,
            dia_index=dia_index,
            subarea_id=subarea_id,
            es_adicional=False
        ).first()
        if existe_misma_subarea:
            flash("Esa subárea ya tiene una tarea REGULAR en este día de la plantilla.", "warning")
            return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    # ✅ Verificar que existe el SOP del tipo seleccionado
    sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()
    if not sop:
        tipo_nombre = "Regular" if tipo_sop == "regular" else "Consecuente"
        flash(f"No existe SOP {tipo_nombre} para esta subárea.", "warning")
        return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    # ✅ VALIDACIÓN de duplicados según tipo
    if tipo_sop == "consecuente":
        # Consecuentes: ILIMITADAS - no validar duplicados
        pass
    else:
        # Regular (incluyendo extraordinario): solo 1 por sop_id en el día
        existe_mismo_sop = PlantillaItem.query.filter_by(
            plantilla_id=plantilla_id,
            dia_index=dia_index,
            subarea_id=subarea_id,
            sop_id=sop.sop_id
        ).first()
        if existe_mismo_sop:
            if nivel == "extraordinario":
                flash("Ya existe una tarea Extraordinario para esta subárea en este día.", "warning")
            else:
                flash("Ya existe una tarea Regular para esta subárea en este día.", "warning")
            return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    # ✅ Crear item con sop_id y es_adicional
    it = PlantillaItem(
        plantilla_id=plantilla_id,
        dia_index=dia_index,
        personal_id=personal_id,
        area_id=area_id,
        subarea_id=subarea_id,
        nivel_limpieza_asignado=nivel,
        sop_id=sop.sop_id,
        es_adicional=es_adicional
    )
    db.session.add(it)
    db.session.commit()

    flash("Actividad agregada.", "success")
    return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))


# =========================
# Borrar item
# =========================
@main_bp.route("/plantillas/item/<int:item_id>/delete", methods=["POST"])
@admin_required
def plantilla_item_delete(item_id: int):
    it = PlantillaItem.query.get_or_404(item_id)
    plantilla_id = it.plantilla_id
    dia_index = it.dia_index
    db.session.delete(it)
    db.session.commit()
    flash("Actividad eliminada.", "success")
    return redirect(url_for("main.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))



# =========================
# (Opcional) Renombrar plantilla
# =========================
@main_bp.route("/plantillas/<int:plantilla_id>/rename", methods=["POST"])
@admin_required
def plantilla_rename(plantilla_id: int):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        flash("Nombre inválido.", "warning")
        return redirect(url_for("main.plantillas_panel", plantilla_id=plantilla_id))

    dup = PlantillaSemanal.query.filter(PlantillaSemanal.nombre == nombre, PlantillaSemanal.plantilla_id != plantilla_id).first()
    if dup:
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("main.plantillas_panel", plantilla_id=plantilla_id))

    plantilla.nombre = nombre
    db.session.commit()
    flash("Nombre actualizado.", "success")
    return redirect(url_for("main.plantillas_panel", plantilla_id=plantilla_id))


# =========================
# Editor de día (Plantilla) — Lun..Sáb sin fecha
# =========================
@main_bp.route("/plantillas/<int:plantilla_id>/dia/<int:dia_index>")
@admin_required
def plantilla_dia(plantilla_id: int, dia_index: int):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

    if dia_index < 0 or dia_index > 5:
        abort(404)

    day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dia_nombre = day_names[dia_index]

    # items del día
    items = (
        PlantillaItem.query
        .options(
            joinedload(PlantillaItem.personal),
            joinedload(PlantillaItem.area),
            joinedload(PlantillaItem.subarea),
        )
        .filter_by(plantilla_id=plantilla_id, dia_index=dia_index)
        .all()
    )

    # ✅ Separar items regulares para el bloqueo
    items_regulares = [it for it in items if not getattr(it, 'es_adicional', False)]
    asignadas_regular_ids = {it.subarea_id for it in items_regulares}

    personal_list = Personal.query.order_by(Personal.nombre.asc()).all()
    areas_list = Area.query.order_by(Area.orden_area.asc(), Area.area_nombre.asc()).all()
    subareas_list = SubArea.query.order_by(SubArea.orden_subarea.asc()).all()

    # Agrupar por persona
    items_por_persona = {}
    for it in items:
        pid = it.personal_id
        if pid not in items_por_persona:
            items_por_persona[pid] = {"persona": it.personal, "items": []}
        items_por_persona[pid]["items"].append(it)

    # Ordenar items dentro de cada persona
    for pid in items_por_persona:
        items_por_persona[pid]["items"].sort(key=lambda x: (
            x.orden or 0,
            x.area.orden_area if x.area else 9999,
            x.subarea.orden_subarea if x.subarea else 9999
        ))

    return render_template(
        "plantilla_dia_form.html",
        plantilla=plantilla,
        dia_index=dia_index,
        dia_nombre=dia_nombre,
        personal_list=personal_list,
        areas_list=areas_list,
        subareas_list=subareas_list,
        asignadas_ids=asignadas_regular_ids,  # Compatibilidad
        asignadas_regular_ids=asignadas_regular_ids,  # ✅ Para box REGULAR
        items_por_persona=items_por_persona,
        hide_nav=True,
    )


# =========================
# AJAX: subáreas por área (SIMPLE, sin fecha/ocupadas)
# =========================
@main_bp.route("/subareas_por_area_simple/<area_id>")
def subareas_por_area_simple(area_id):
    subareas = (
        SubArea.query
        .filter_by(area_id=area_id)
        .order_by(SubArea.orden_subarea.asc(), SubArea.subarea_nombre.asc())
        .all()
    )
    return jsonify([
        {"id": s.subarea_id, "nombre": s.subarea_nombre}
        for s in subareas
    ])


# =========================
# HELPERS: Crear SOP
# =========================
def _strip_prefix(x: str, prefix: str) -> str:
    return x[len(prefix):] if x and x.startswith(prefix) else x

def nivel_letter(nivel_id: int) -> str:
    # BD: 1=B, 2=M, 3=P
    return {1: "B", 2: "M", 3: "P"}.get(int(nivel_id), "B")

def make_sop_id(subarea_id: str, tipo_sop: str) -> str:
    """Genera sop_id: SP-{subarea_id}-R o SP-{subarea_id}-C"""
    sufijo = "R" if tipo_sop == "regular" else "C"
    return f"SP-{subarea_id}-{sufijo}"


def make_sf_id(sop_id: str, fraccion_id: str) -> str:
    # "SP-AD-DI-BA-001" + "FR-SE-001" -> "SF-AD-DI-BA-001-SE-001"
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"SF-{sop_core}-{fr_core}"

def make_sd_id(sop_id: str, fraccion_id: str, nivel_id: int) -> str:
    # "SP-AD-DI-BA-001" + "FR-SE-001" + 1 -> "SD-AD-DI-BA-001-SE-001-B"
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"SD-{sop_core}-{fr_core}-{nivel_letter(nivel_id)}"

def make_es_id(sop_id: str, fraccion_id: str, nivel_id: int) -> str:
    # "SP-AD-DI-BA-001" + "FR-TL-001" + 3 -> "ES-AD-DI-BA-001-TL-001-P"
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"ES-{sop_core}-{fr_core}-{nivel_letter(nivel_id)}"


# =========================
# SOP PANEL
# =========================
@main_bp.route("/sop")
@admin_required
def sop_panel():
    # ============================================================================
    # PARTE 1: SOP REGULAR/CONSECUENTE (EXISTENTE)
    # ============================================================================
    area_id = (request.args.get("area_id") or "").strip()
    subarea_id = (request.args.get("subarea_id") or "").strip()
    tipo_sop = (request.args.get("tipo_sop") or "regular").strip()

    # Validar tipo_sop
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    # Nivel seleccionado
    nivel = canon_nivel(request.args.get("nivel")) or "basica"
    nivel_id = nivel_to_id(nivel) or 1

    areas = Area.query.order_by(Area.orden_area.asc(), Area.area_nombre.asc()).all()

    subareas = []
    if area_id:
        subareas = (
            SubArea.query
            .filter_by(area_id=area_id)
            .order_by(SubArea.orden_subarea.asc(), SubArea.subarea_nombre.asc())
            .all()
        )

    sop = None
    has_fracciones = False
    has_nivel = False

    if subarea_id:
        sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()

        if sop and sop.sop_fracciones and len(sop.sop_fracciones) > 0:
            has_fracciones = True

        # Existe "nivel" si hay al menos un detalle para ese nivel
        if sop:
            has_nivel = (
                db.session.query(SopFraccionDetalle.sop_fraccion_detalle_id)
                .join(SopFraccion, SopFraccion.sop_fraccion_id == SopFraccionDetalle.sop_fraccion_id)
                .filter(
                    and_(
                        SopFraccion.sop_id == sop.sop_id,
                        SopFraccionDetalle.nivel_limpieza_id == nivel_id
                    )
                )
                .first()
                is not None
            )

    # ============================================================================
    # PARTE 2: SOP EVENTO (NUEVO)
    # ============================================================================
    evento_tipo_id = (request.args.get("evento_tipo_id") or "").strip()
    caso_id = (request.args.get("caso_id") or "").strip()

    # Cargar todos los tipos de evento
    eventos = EventoCatalogo.query.order_by(EventoCatalogo.nombre.asc()).all()

    # Cargar casos del tipo seleccionado
    casos = []
    if evento_tipo_id:
        casos = (
            CasoCatalogo.query
            .filter_by(evento_tipo_id=evento_tipo_id)
            .order_by(CasoCatalogo.nombre.asc())
            .all()
        )

    # Buscar si existe SOP de evento
    sop_evento = None
    has_fracciones_evento = False

    if evento_tipo_id and caso_id:
        sop_evento = SopEvento.query.filter_by(
            evento_tipo_id=evento_tipo_id,
            caso_id=caso_id
        ).first()

        # Verificar si tiene fracciones configuradas
        if sop_evento and sop_evento.detalles and len(sop_evento.detalles) > 0:
            has_fracciones_evento = True

    # ============================================================================
    # RENDER
    # ============================================================================
    return render_template(
        "sop_panel.html",
        # Variables SOP Regular
        areas=areas,
        subareas=subareas,
        area_id=area_id,
        subarea_id=subarea_id,
        sop=sop,
        has_fracciones=has_fracciones,
        has_nivel=has_nivel,
        nivel=nivel,
        nivel_id=nivel_id,
        tipo_sop=tipo_sop,
        
        # Variables SOP Evento
        eventos=eventos,
        casos=casos,
        evento_tipo_id=evento_tipo_id,
        caso_id=caso_id,
        sop_evento=sop_evento,
        has_fracciones_evento=has_fracciones_evento,
    )



# =========================
# Helpers IDs SOP (formato que me pasaste)
# =========================
def _fr_suffix(fraccion_id: str) -> str:
    # "FR-SE-001" -> "SE-001"
    if not fraccion_id:
        return ""
    return fraccion_id[3:] if fraccion_id.startswith("FR-") else fraccion_id

def sop_id_from_subarea(subarea_id: str) -> str:
    # "AD-DI-BA-001" -> "SP-AD-DI-BA-001"
    return f"SP-{subarea_id}"

def sop_fraccion_id_from(sop_id: str, fraccion_id: str) -> str:
    # "SP-AD-DI-BA-001" + "FR-SE-001" -> "SF-AD-DI-BA-001-SE-001"
    base = sop_id[3:] if sop_id.startswith("SP-") else sop_id
    return f"SF-{base}-{_fr_suffix(fraccion_id)}"

def nivel_letter(nivel_limpieza_id: int) -> str:
    return {1: "B", 2: "M", 3: "P"}.get(int(nivel_limpieza_id), "X")

def sop_fraccion_detalle_id_from(sop_fraccion_id: str, nivel_limpieza_id: int) -> str:
    # "SF-AD-DI-BA-001-SE-001" + 1 -> "SD-AD-DI-BA-001-SE-001-B"
    base = sop_fraccion_id[3:] if sop_fraccion_id.startswith("SF-") else sop_fraccion_id
    return f"SD-{base}-{nivel_letter(nivel_limpieza_id)}"



# =========================
# SOP: asiganar detalles
# =========================
@main_bp.route("/sop/<sop_id>/detalles", methods=["GET", "POST"])
@admin_required
def sop_detalles(sop_id):
    # ✅ AÑADIR: Capturar tipo_sop
    tipo_sop = (request.args.get("tipo_sop") or request.form.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"
    
    # nivel por query o form
    nivel = (request.args.get("nivel") or request.form.get("nivel") or "").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    nivel_obj = NivelLimpieza.query.filter_by(nombre=nivel).first()
    if not nivel_obj:
        flash("Nivel de limpieza inválido.", "error")
        return redirect(url_for("main.sop_panel"))

    nivel_id = int(nivel_obj.nivel_limpieza_id)

    sop = SOP.query.filter_by(sop_id=sop_id).first_or_404()
    subarea = sop.subarea

    # ✅ Todas las fracciones del SOP (global)
    sop_fracciones_all = (
        SopFraccion.query
        .filter_by(sop_id=sop_id)
        .order_by(SopFraccion.orden.asc())
        .all()
    )

    if not sop_fracciones_all:
        flash("Este SOP no tiene fracciones todavía.", "warning")
        return redirect(url_for(
            "main.sop_panel",
            area_id=subarea.area_id,
            subarea_id=subarea.subarea_id,
            nivel=nivel,
            tipo_sop=tipo_sop  # ✅ AÑADIR
        ))

    # ✅ Fracciones que YA tienen detalle para este nivel
    sop_fracciones_nivel = (
        SopFraccion.query
        .join(SopFraccionDetalle, SopFraccionDetalle.sop_fraccion_id == SopFraccion.sop_fraccion_id)
        .filter(
            SopFraccion.sop_id == sop_id,
            SopFraccionDetalle.nivel_limpieza_id == nivel_id
        )
        .order_by(SopFraccion.orden.asc())
        .all()
    )

    # ✅ Si el nivel aún NO está configurado: render vacío (sin redirigir)
    if not sop_fracciones_nivel:
        recetas = Receta.query.order_by(Receta.nombre.asc()).all()
        consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
        kits = []  # no aplica aún
        return render_template(
            "sop_detalles.html",
            sop=sop,
            subarea=subarea,
            nivel=nivel,
            nivel_id=nivel_id,
            nivel_obj=nivel_obj,
            tipo_sop=tipo_sop,  # ✅ AÑADIR
            sop_fracciones=[],
            sf_actual=None,
            detalle=None,
            kits=kits,
            recetas=recetas,
            consumos=consumos,
            elemento_sets=[],
            elemento_detalles=[],
            metodologia_base=None,
            hide_nav=True,
        )

    # ✅ ya hay fracciones para este nivel -> sidebar solo con esas
    sop_fracciones = sop_fracciones_nivel

    sop_fraccion_id = (request.args.get("sop_fraccion_id") or request.form.get("sop_fraccion_id") or "").strip()
    sf_actual = next((x for x in sop_fracciones if x.sop_fraccion_id == sop_fraccion_id), sop_fracciones[0])
    fr = sf_actual.fraccion  # puede ser None si no hay relación cargada, pero normalmente sí

    recetas = Receta.query.order_by(Receta.nombre.asc()).all()
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()

    # detalle del nivel
    detalle = (
        SopFraccionDetalle.query
        .filter_by(sop_fraccion_id=sf_actual.sop_fraccion_id, nivel_limpieza_id=nivel_id)
        .first()
    )
    if not detalle:
        detalle = SopFraccionDetalle(
            sop_fraccion_detalle_id=make_sd_id(sop.sop_id, fr.fraccion_id, nivel_id),
            sop_fraccion_id=sf_actual.sop_fraccion_id,
            nivel_limpieza_id=nivel_id,
        )
        db.session.add(detalle)
        db.session.flush()

    # Metodología (solo lectura)
    metodologia_base = None
    met = Metodologia.query.filter_by(fraccion_id=fr.fraccion_id, nivel_limpieza_id=nivel_id).first()
    if met and met.metodologia_base:
        metodologia_base = met.metodologia_base

    # Elemento sets válidos para este SOP específico
    sop_core = sop.sop_id.replace("SP-", "ES-")
    elemento_sets = (
        ElementoSet.query
        .filter(
            ElementoSet.subarea_id == subarea.subarea_id,
            ElementoSet.fraccion_id == fr.fraccion_id,
            ElementoSet.nivel_limpieza_id == nivel_id,
            ElementoSet.elemento_set_id.like(f"{sop_core}-%")
        )
        .order_by(ElementoSet.elemento_set_id.asc())
        .all()
    )

    elemento_detalles = []
    if detalle.elemento_set_id:
        elemento_detalles = (
            ElementoDetalle.query
            .filter_by(elemento_set_id=detalle.elemento_set_id)
            .order_by(ElementoDetalle.orden.asc())
            .all()
        )

    kits = (
        Kit.query
        .filter(
            Kit.fraccion_id == fr.fraccion_id,
            or_(Kit.nivel_limpieza_id == None, Kit.nivel_limpieza_id == nivel_id)
        )
        .order_by(Kit.nombre.asc())
        .all()
    )

    # =========================
    # ✅ POST: Guardar detalle
    # =========================
    if request.method == "POST":
        mode = (request.form.get("mode") or "directo").strip().lower()

        # tiempo
        tiempo_raw = (request.form.get("tiempo_unitario_min") or "").strip()
        if tiempo_raw == "":
            detalle.tiempo_unitario_min = None
        else:
            try:
                detalle.tiempo_unitario_min = float(tiempo_raw)
            except ValueError:
                flash("Tiempo inválido.", "warning")
                return redirect(url_for("main.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))  # ✅ AÑADIR tipo_sop

        if mode == "elementos":
            # Regla BD: si elemento_set_id != NULL => kit_id y receta_id deben ser NULL
            detalle.kit_id = None
            detalle.receta_id = None

            # Recomendación: consumo directo también en NULL (para no mezclar directo vs elementos)
            detalle.consumo_id = None

            es_id = (request.form.get("elemento_set_id") or "").strip() or None

            # Si no seleccionó, usar/crear default por convención humana
            if not es_id:
                es_id = make_es_id(sop.sop_id, fr.fraccion_id, nivel_id)

                es = ElementoSet.query.filter_by(elemento_set_id=es_id).first()
                if not es:
                    es = ElementoSet(
                        elemento_set_id=es_id,
                        subarea_id=subarea.subarea_id,
                        fraccion_id=fr.fraccion_id,
                        nivel_limpieza_id=nivel_id,
                        nombre=f"{subarea.subarea_nombre} · {fr.fraccion_nombre} ({nivel})"
                    )
                    db.session.add(es)

            else:
                # Validación: que el elemento_set_id pertenezca a esta subarea+fraccion+nivel
                es_ok = ElementoSet.query.filter_by(
                    elemento_set_id=es_id,
                    subarea_id=subarea.subarea_id,
                    fraccion_id=fr.fraccion_id,
                    nivel_limpieza_id=nivel_id,
                ).first()
                if not es_ok:
                    flash("Elemento Set inválido para esta subárea/fracción/nivel.", "warning")
                    return redirect(url_for("main.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))  # ✅ AÑADIR tipo_sop

            detalle.elemento_set_id = es_id

        else:
            # Modo directo: no usar elemento_set
            detalle.elemento_set_id = None

            detalle.kit_id = (request.form.get("kit_id") or "").strip() or None
            detalle.receta_id = (request.form.get("receta_id") or "").strip() or None
            detalle.consumo_id = (request.form.get("consumo_id") or "").strip() or None

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Si quieres ver el error real en consola:
            print("💥 ERROR COMMIT sop_detalles:", repr(e))
            flash("Error guardando detalle (revisa consola).", "error")
            return redirect(url_for("main.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))  # ✅ AÑADIR tipo_sop

        flash("✅ Detalle guardado.", "success")
        # ✅ Importante: aquí verás POST 302 en logs (y luego GET 200)
        return redirect(url_for("main.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))  # ✅ AÑADIR tipo_sop

    # GET
    return render_template(
        "sop_detalles.html",
        sop=sop,
        subarea=subarea,
        nivel=nivel,
        nivel_id=nivel_id,
        nivel_obj=nivel_obj,
        tipo_sop=tipo_sop,  # ✅ AÑADIR
        sop_fracciones=sop_fracciones,
        sf_actual=sf_actual,
        detalle=detalle,
        kits=kits,
        recetas=recetas,
        consumos=consumos,
        elemento_sets=elemento_sets,
        elemento_detalles=elemento_detalles,
        metodologia_base=metodologia_base,
        hide_nav=True,
    )

# ============================================================
# SOP FRACCIONES EDIT
# ============================================================
@main_bp.route("/sop/<sop_id>/fracciones")
@admin_required
def sop_fracciones_edit(sop_id):
    nivel = (request.args.get("nivel") or "media").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    # ✅ AÑADIR: Capturar tipo_sop
    tipo_sop = (request.args.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    nivel_id = nivel_to_id(nivel) or 2

    sop = SOP.query.filter_by(sop_id=sop_id).first()
    if not sop:
        flash("SOP no encontrado.", "error")
        return redirect(url_for("main.sop_panel"))
    
    tipo_sop = sop.tipo_sop

    has_level = (
        db.session.query(SopFraccionDetalle.sop_fraccion_detalle_id)
        .join(SopFraccion, SopFraccion.sop_fraccion_id == SopFraccionDetalle.sop_fraccion_id)
        .filter(
            SopFraccion.sop_id == sop_id,
            SopFraccionDetalle.nivel_limpieza_id == nivel_id
        )
        .first()
        is not None
    )

    if not has_level:
        # ✅ CORREGIDO: Añadir tipo_sop
        return redirect(url_for("main.sop_crear", subarea_id=sop.subarea_id, nivel=nivel, tipo_sop=tipo_sop))

    first_sf = (
        SopFraccion.query
        .join(SopFraccionDetalle, SopFraccionDetalle.sop_fraccion_id == SopFraccion.sop_fraccion_id)
        .filter(
            SopFraccion.sop_id == sop_id,
            SopFraccionDetalle.nivel_limpieza_id == nivel_id
        )
        .order_by(SopFraccion.orden.asc())
        .first()
    )

    # ✅ CORREGIDO: Añadir tipo_sop
    return redirect(url_for(
        "main.sop_detalles",
        sop_id=sop_id,
        nivel=nivel,
        tipo_sop=tipo_sop,  # ← NUEVO
        sop_fraccion_id=first_sf.sop_fraccion_id
    ))

# =========================
# SOP: crear (seleccionar fracciones por nivel)
# =========================
@main_bp.route("/sop/crear/<subarea_id>", methods=["GET", "POST"])
@admin_required
def sop_crear(subarea_id):
    # tipo_sop y nivel vienen del panel o query
    tipo_sop = (request.args.get("tipo_sop") or request.form.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    nivel = canon_nivel(request.args.get("nivel")) or canon_nivel(request.form.get("nivel")) or "basica"
    nivel_id = nivel_to_id(nivel) or 1

    subarea = (
        SubArea.query.options(joinedload(SubArea.area))
        .filter_by(subarea_id=subarea_id)
        .first_or_404()
    )

    # Obtener grupo_fracciones del área padre
    grupo_fracciones = subarea.area.grupo_fracciones if subarea.area else None

    # Generar sop_id esperado
    sop_id = make_sop_id(subarea_id, tipo_sop)
    
    # Buscar SOP existente
    sop = SOP.query.filter_by(sop_id=sop_id).first()

    if sop:
        tipo_sop = sop.tipo_sop

    if nivel_id == 4:  # Extraordinario
        # Mostrar fracciones con metodología Profundo (3) O Extraordinario (4)
        niveles_validos = [3, 4]
    else:
        # Para otros niveles, solo ese nivel específico
        niveles_validos = [nivel_id]

    # Fracciones disponibles: filtrar por grupo_fracciones Y que tengan metodología para ese nivel
    fracciones_query = (
        Fraccion.query
        .join(Metodologia, Metodologia.fraccion_id == Fraccion.fraccion_id)
        .filter(Metodologia.nivel_limpieza_id.in_(niveles_validos))  # ← Usar IN
        .distinct()
    )
        
    # Filtrar por grupo_fracciones si existe
    if grupo_fracciones:
        fracciones_query = fracciones_query.filter(Fraccion.grupo_fracciones == grupo_fracciones)
    
    fracciones = fracciones_query.order_by(Fraccion.fraccion_id.asc()).all()

    # SELECTED + ORDEN MAP para este nivel
    selected_ids = set()
    orden_map = {}

    if sop:
        sfs_nivel = (
            SopFraccion.query
            .join(SopFraccionDetalle, SopFraccionDetalle.sop_fraccion_id == SopFraccion.sop_fraccion_id)
            .filter(
                SopFraccion.sop_id == sop.sop_id,
                SopFraccionDetalle.nivel_limpieza_id == nivel_id
            )
            .all()
        )
        selected_ids = {sf.fraccion_id for sf in sfs_nivel}
        orden_map = {sf.fraccion_id: (sf.orden or 1000) for sf in sfs_nivel}

    # POST: guardar cambios del nivel
    if request.method == "POST":
        selected = request.form.getlist("fraccion_id")
        selected_set = set(selected)

        if not selected:
            flash("Selecciona al menos 1 fracción.", "warning")
            return redirect(url_for("main.sop_crear", subarea_id=subarea_id, nivel=nivel, tipo_sop=tipo_sop))

        # 1) crear SOP si no existe
        if not sop:
            sop = SOP(
                sop_id=sop_id,
                subarea_id=subarea_id,
                tipo_sop=tipo_sop
            )
            db.session.add(sop)
            db.session.flush()
            tipo_sop = sop.tipo_sop

        # 2) calcular qué se removió (solo para este nivel)
        prev_selected = selected_ids.copy() if selected_ids else set()
        to_remove = prev_selected - selected_set

        if to_remove:
            sfs_to_remove = (
                SopFraccion.query
                .filter(
                    SopFraccion.sop_id == sop.sop_id,
                    SopFraccion.fraccion_id.in_(list(to_remove))
                )
                .all()
            )

            for sf in sfs_to_remove:
                # ✅ NUEVO: Primero borrar ElementoSet de ESTE nivel
                for fr_id in to_remove:
                    # Generar el elemento_set_id esperado
                    es_id = make_es_id(sop.sop_id, fr_id, nivel_id)
                    
                    # Borrar ElementoSet (cascade borrará ElementoDetalle automáticamente)
                    es = ElementoSet.query.filter_by(elemento_set_id=es_id).first()
                    if es:
                        db.session.delete(es)
                
                # Borrar detalle de ESTE nivel
                SopFraccionDetalle.query.filter_by(
                    sop_fraccion_id=sf.sop_fraccion_id,
                    nivel_limpieza_id=nivel_id
                ).delete()

                # si ya no quedan detalles en ningún nivel → borrar SopFraccion
                still_has_any = (
                    db.session.query(SopFraccionDetalle.sop_fraccion_detalle_id)
                    .filter(SopFraccionDetalle.sop_fraccion_id == sf.sop_fraccion_id)
                    .first()
                    is not None
                )
                if not still_has_any:
                    db.session.delete(sf)

        # 3) upsert seleccionadas: actualizar orden + asegurar detalle del nivel
        for fr_id in selected:
            orden_raw = (request.form.get(f"orden_{fr_id}") or "").strip()
            orden = int(orden_raw) if orden_raw.isdigit() else 1000

            sf = SopFraccion.query.filter_by(sop_id=sop.sop_id, fraccion_id=fr_id).first()
            if not sf:
                sf = SopFraccion(
                    sop_fraccion_id=make_sf_id(sop.sop_id, fr_id),
                    sop_id=sop.sop_id,
                    fraccion_id=fr_id,
                    orden=orden
                )
                db.session.add(sf)
                db.session.flush()
            else:
                sf.orden = orden

            sd = SopFraccionDetalle.query.filter_by(
                sop_fraccion_id=sf.sop_fraccion_id,
                nivel_limpieza_id=nivel_id
            ).first()

            if not sd:
                sd = SopFraccionDetalle(
                    sop_fraccion_detalle_id=make_sd_id(sop.sop_id, fr_id, nivel_id),
                    sop_fraccion_id=sf.sop_fraccion_id,
                    nivel_limpieza_id=nivel_id,
                    tiempo_unitario_min=None,
                )
                db.session.add(sd)

        db.session.commit()
        flash(f"✅ Fracciones guardadas para nivel {nivel}.", "success")
        return redirect(url_for("main.sop_fracciones_edit", sop_id=sop.sop_id, nivel=nivel, tipo_sop=tipo_sop))

    # GET
    return render_template(
        "sop_crear.html",
        subarea=subarea,
        sop=sop,
        sop_id=sop_id,
        nivel=nivel,
        nivel_id=nivel_id,
        tipo_sop=tipo_sop,
        fracciones=fracciones,
        selected_ids=selected_ids,
        orden_map=orden_map,
    )


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas.", "warning")
            return render_template("login.html"), 401

        login_user(user)

        # admin al home, operativo a su ruta
        if user.role == "admin":
            return redirect(url_for("main.home"))
        return redirect(url_for("main.mi_ruta"))

    return render_template("login.html")


@main_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("main.login"))


# ======================================================
# REEMPLAZAR la función mi_ruta existente en routes.py
# ======================================================
@main_bp.route("/mi_ruta")
@login_required
def mi_ruta():
    # Si es admin, no debe entrar aquí
    if getattr(current_user, "role", None) == "admin":
        return redirect(url_for("main.home_admin_panel"))

    # Operativo debe estar ligado a un Personal
    if not getattr(current_user, "personal_id", None):
        abort(403)

    hoy = date.today()
    hoy_str = hoy.strftime("%Y-%m-%d")

    # Busca el día en BD
    dia = LanzamientoDia.query.filter_by(fecha=hoy).first()

    tareas = []
    tiempo_total = 0.0
    checks_map = {}  # {tarea_id: "HH:MM"}

    if dia:
        # ✅ CAMBIO: Cargar relaciones para eventos y casos
        tareas = (
            LanzamientoTarea.query
            .filter_by(dia_id=dia.dia_id, personal_id=current_user.personal_id)
            .options(
                joinedload(LanzamientoTarea.area),
                joinedload(LanzamientoTarea.subarea),
                joinedload(LanzamientoTarea.sop_evento).joinedload(SopEvento.evento_catalogo),
                joinedload(LanzamientoTarea.sop_evento).joinedload(SopEvento.caso_catalogo),
            )
            .order_by(LanzamientoTarea.orden)
            .all()
        )
        
        # Obtener checks de estas tareas
        tarea_ids = [t.tarea_id for t in tareas]
        if tarea_ids:
            checks = TareaCheck.query.filter(TareaCheck.tarea_id.in_(tarea_ids)).all()
            checks_map = {c.tarea_id: c.checked_at.strftime("%H:%M") for c in checks}
        
        # Calcular tiempo total
        try:
            tiempo_total = sum(float(calcular_tiempo_tarea(t)) for t in tareas)
        except Exception:
            tiempo_total = 0.0

    # Calcular progreso
    total_tareas = len(tareas)
    completadas = len(checks_map)
    progreso_pct = round((completadas / total_tareas * 100) if total_tareas > 0 else 0)

    return render_template(
        "mi_ruta.html",
        hoy=hoy,
        hoy_str=hoy_str,
        tareas=tareas,
        tiempo_total=round(tiempo_total, 2),
        checks_map=checks_map,
        total_tareas=total_tareas,
        completadas=completadas,
        progreso_pct=progreso_pct,
    )


# =========================
# API: Reordenar tareas (drag & drop)
# =========================
@main_bp.route("/api/reordenar-tareas", methods=["POST"])
@admin_required
def reordenar_tareas():
    data = request.get_json()
    if not data or "orden" not in data:
        return {"error": "Datos inválidos"}, 400
    
    for item in data["orden"]:
        tarea_id = item.get("tarea_id")
        nuevo_orden = item.get("orden")
        tarea = LanzamientoTarea.query.get(tarea_id)
        if tarea:
            tarea.orden = nuevo_orden
    
    db.session.commit()
    return {"success": True}, 200


# =========================
# API: Reordenar items de plantilla (drag & drop)
# =========================
@main_bp.route("/api/reordenar-plantilla-items", methods=["POST"])
@admin_required
def reordenar_plantilla_items():
    data = request.get_json()
    if not data or "orden" not in data:
        return {"error": "Datos inválidos"}, 400
    
    for item in data["orden"]:
        item_id = item.get("item_id")
        nuevo_orden = item.get("orden")
        plantilla_item = PlantillaItem.query.get(item_id)
        if plantilla_item:
            plantilla_item.orden = nuevo_orden
    
    db.session.commit()
    return {"success": True}, 200


from datetime import datetime, timezone, timedelta


# ======================================================
# FUNCIÓN HELPER: Hora CDMX
# ======================================================
def now_cdmx():
    """Retorna datetime actual en CDMX (CST = UTC-6)"""
    utc_now = datetime.now(timezone.utc)
    cdmx_offset = timedelta(hours=-6)
    return (utc_now + cdmx_offset).replace(tzinfo=None)


# ======================================================
# API: Marcar tarea/subárea como completada (Operativo)
# ======================================================
@main_bp.route("/api/tarea/<int:tarea_id>/check", methods=["POST"])
@login_required
def marcar_tarea_check(tarea_id):
    # Solo operativos pueden marcar sus propias tareas
    if current_user.role == "admin":
        return {"error": "Admin no puede marcar tareas"}, 403
    
    tarea = LanzamientoTarea.query.get_or_404(tarea_id)
    
    # Verificar que la tarea pertenece al operativo
    if tarea.personal_id != current_user.personal_id:
        return {"error": "Esta tarea no te pertenece"}, 403
    
    # Verificar que la tarea es de hoy
    hoy = date.today()
    dia = LanzamientoDia.query.get(tarea.dia_id)
    if not dia or dia.fecha != hoy:
        return {"error": "Solo puedes marcar tareas de hoy"}, 403
    
    # Verificar si ya existe un check
    existing = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
    if existing:
        return {
            "error": "Tarea ya marcada", 
            "checked_at": existing.checked_at.strftime("%H:%M")
        }, 400
    
    # Crear el check
    check = TareaCheck(
        tarea_id=tarea_id,
        checked_at=now_cdmx(),
        user_id=current_user.user_id
    )
    db.session.add(check)
    db.session.commit()
    
    return {
        "success": True, 
        "check_id": check.check_id,
        "checked_at": check.checked_at.strftime("%H:%M")
    }, 201


# ======================================================
# API: Desmarcar tarea/subárea (Operativo)
# ======================================================
@main_bp.route("/api/tarea/<int:tarea_id>/check", methods=["DELETE"])
@login_required
def desmarcar_tarea_check(tarea_id):
    # Solo operativos pueden desmarcar sus propias tareas
    if current_user.role == "admin":
        return {"error": "Admin no puede desmarcar tareas"}, 403
    
    tarea = LanzamientoTarea.query.get_or_404(tarea_id)
    
    # Verificar que la tarea pertenece al operativo
    if tarea.personal_id != current_user.personal_id:
        return {"error": "Esta tarea no te pertenece"}, 403
    
    # Verificar que la tarea es de hoy
    hoy = date.today()
    dia = LanzamientoDia.query.get(tarea.dia_id)
    if not dia or dia.fecha != hoy:
        return {"error": "Solo puedes modificar tareas de hoy"}, 403
    
    # Buscar y borrar el check
    check = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
    if not check:
        return {"error": "Tarea no estaba marcada"}, 404
    
    db.session.delete(check)
    db.session.commit()
    
    return {"success": True}, 200


# ============================================================
# 3. NUEVOS ENDPOINTS AJAX (agregar al final del archivo)
# ============================================================
@main_bp.route("/api/verificar_sop/<subarea_id>/<tipo_sop>")
@admin_required
def verificar_sop_existe(subarea_id, tipo_sop):
    """
    Verifica si existe un SOP del tipo especificado.
    
    ✅ NOTA: "extraordinario" se mapea a "regular" en el frontend,
    por lo que aquí tipo_sop será "regular" o "consecuente".
    """
    if tipo_sop not in ("regular", "consecuente"):
        return jsonify({"existe": False, "sop_id": None, "error": "Tipo SOP inválido"})
    
    sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()
    
    return jsonify({
        "existe": sop is not None,
        "sop_id": sop.sop_id if sop else None
    })

@main_bp.route("/api/subareas_con_sop/<area_id>")
@admin_required
def subareas_con_sop(area_id):
    """
    Retorna subáreas con información de SOPs disponibles.
    Para el box ADICIONAL (sin bloqueo de ocupadas).
    """
    subareas = SubArea.query.filter_by(area_id=area_id).order_by(SubArea.orden_subarea.asc()).all()
    
    result = []
    for s in subareas:
        sop_regular = SOP.query.filter_by(subarea_id=s.subarea_id, tipo_sop="regular").first()
        sop_consecuente = SOP.query.filter_by(subarea_id=s.subarea_id, tipo_sop="consecuente").first()
        
        result.append({
            "id": s.subarea_id,
            "nombre": s.subarea_nombre,
            "tiene_regular": sop_regular is not None,
            "tiene_consecuente": sop_consecuente is not None,
        })
    
    return jsonify(result)


@main_bp.route('/api/sop-evento-fracciones', methods=['GET'])
def listar_fracciones_evento():
    """
    GET /api/sop-evento-fracciones
    
    Retorna todas las fracciones de evento con su metodología y pasos.
    """
    try:
        fracciones = SopEventoFraccion.query.all()
        
        resultado = []
        for fraccion in fracciones:
            # Obtener metodología y pasos
            metodologia = fraccion.metodologia
            
            fraccion_data = {
                'fraccion_evento_id': fraccion.fraccion_evento_id,
                'nombre': fraccion.nombre,
                'descripcion': fraccion.descripcion,
                'metodologia': None
            }
            
            # Agregar metodología si existe
            if metodologia:
                pasos = [{
                    'paso_id': paso.paso_id,
                    'numero_paso': paso.numero_paso,
                    'descripcion': paso.descripcion
                } for paso in metodologia.pasos]
                
                fraccion_data['metodologia'] = {
                    'metodologia_fraccion_id': metodologia.metodologia_fraccion_id,
                    'nombre': metodologia.nombre,
                    'descripcion': metodologia.descripcion,
                    'pasos': pasos,
                    'total_pasos': len(pasos)
                }
            
            resultado.append(fraccion_data)
        
        return jsonify({
            'success': True,
            'data': resultado,
            'total': len(resultado)
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al listar fracciones: {str(e)}'
        }), 500


# ============================================================================
# 2. OBTENER DETALLE DE UNA FRACCIÓN
# ============================================================================
@main_bp.route('/api/sop-evento-fracciones/<fraccion_id>', methods=['GET'])
def obtener_fraccion_evento(fraccion_id):
    """
    GET /api/sop-evento-fracciones/<fraccion_id>
    
    Retorna el detalle completo de una fracción con su metodología y pasos.
    """
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({
                'success': False,
                'message': 'Fracción no encontrada'
            }), 404
        
        metodologia = fraccion.metodologia
        
        fraccion_data = {
            'fraccion_evento_id': fraccion.fraccion_evento_id,
            'nombre': fraccion.nombre,
            'descripcion': fraccion.descripcion,
            'metodologia': None
        }
        
        # Agregar metodología si existe
        if metodologia:
            pasos = [{
                'paso_id': paso.paso_id,
                'numero_paso': paso.numero_paso,
                'descripcion': paso.descripcion
            } for paso in metodologia.pasos]
            
            fraccion_data['metodologia'] = {
                'metodologia_fraccion_id': metodologia.metodologia_fraccion_id,
                'nombre': metodologia.nombre,
                'descripcion': metodologia.descripcion,
                'pasos': pasos,
                'total_pasos': len(pasos)
            }
        
        return jsonify({
            'success': True,
            'data': fraccion_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener fracción: {str(e)}'
        }), 500


# ============================================================================
# 3. CREAR NUEVA FRACCIÓN CON METODOLOGÍA Y PASOS
# ============================================================================
@main_bp.route('/api/sop-evento-fracciones', methods=['POST'])
def crear_fraccion_evento():
    """
    POST /api/sop-evento-fracciones
    
    Crea una nueva fracción de evento con su metodología y pasos.
    
    Body:
    {
        "fraccion_evento_id": "FE-TR-001",
        "nombre": "Trapear área afectada",
        "descripcion": "Trapear y desinfectar el área",
        "metodologia": {
            "metodologia_fraccion_id": "MEF-TR-001",
            "nombre": "Metodología de Trapeo",
            "descripcion": "Proceso completo de trapeo",
            "pasos": [
                {
                    "numero_paso": 1,
                    "descripcion": "Preparar solución desinfectante"
                },
                {
                    "numero_paso": 2,
                    "descripcion": "Trapear en movimientos circulares"
                }
            ]
        }
    }
    """
    try:
        data = request.get_json()
        
        # Validaciones básicas
        if not data.get('fraccion_evento_id'):
            return jsonify({
                'success': False,
                'message': 'fraccion_evento_id es requerido'
            }), 400
        
        if not data.get('nombre'):
            return jsonify({
                'success': False,
                'message': 'nombre es requerido'
            }), 400
        
        # Verificar que no exista la fracción
        if SopEventoFraccion.query.get(data['fraccion_evento_id']):
            return jsonify({
                'success': False,
                'message': 'Ya existe una fracción con ese ID'
            }), 400
        
        # Crear fracción
        nueva_fraccion = SopEventoFraccion(
            fraccion_evento_id=data['fraccion_evento_id'],
            nombre=data['nombre'],
            descripcion=data.get('descripcion')
        )
        
        db.session.add(nueva_fraccion)
        
        # Crear metodología si viene en el request
        metodologia_data = data.get('metodologia')
        if metodologia_data:
            if not metodologia_data.get('metodologia_fraccion_id'):
                return jsonify({
                    'success': False,
                    'message': 'metodologia_fraccion_id es requerido'
                }), 400
            
            # Verificar que no exista la metodología
            if MetodologiaEventoFraccion.query.get(metodologia_data['metodologia_fraccion_id']):
                return jsonify({
                    'success': False,
                    'message': 'Ya existe una metodología con ese ID'
                }), 400
            
            nueva_metodologia = MetodologiaEventoFraccion(
                metodologia_fraccion_id=metodologia_data['metodologia_fraccion_id'],
                fraccion_evento_id=data['fraccion_evento_id'],
                nombre=metodologia_data.get('nombre', data['nombre']),
                descripcion=metodologia_data.get('descripcion')
            )
            
            db.session.add(nueva_metodologia)
            
            # Crear pasos si vienen en el request
            pasos = metodologia_data.get('pasos', [])
            for paso_data in pasos:
                nuevo_paso = MetodologiaEventoFraccionPaso(
                    metodologia_fraccion_id=metodologia_data['metodologia_fraccion_id'],
                    numero_paso=paso_data['numero_paso'],
                    descripcion=paso_data['descripcion']
                )
                db.session.add(nuevo_paso)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Fracción creada exitosamente',
            'data': {
                'fraccion_evento_id': nueva_fraccion.fraccion_evento_id,
                'nombre': nueva_fraccion.nombre
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al crear fracción: {str(e)}'
        }), 500


# ============================================================================
# 4. EDITAR FRACCIÓN CON METODOLOGÍA Y PASOS
# ============================================================================
@main_bp.route('/api/sop-evento-fracciones/<fraccion_id>', methods=['PUT'])
def editar_fraccion_evento(fraccion_id):
    """
    PUT /api/sop-evento-fracciones/<fraccion_id>
    
    Edita una fracción existente con su metodología y pasos.
    
    Body: (mismo formato que POST)
    """
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({
                'success': False,
                'message': 'Fracción no encontrada'
            }), 404
        
        data = request.get_json()
        
        # Actualizar fracción
        if 'nombre' in data:
            fraccion.nombre = data['nombre']
        if 'descripcion' in data:
            fraccion.descripcion = data['descripcion']
        
        # Actualizar metodología si viene en el request
        metodologia_data = data.get('metodologia')
        if metodologia_data:
            metodologia = fraccion.metodologia
            
            if metodologia:
                # Actualizar metodología existente
                if 'nombre' in metodologia_data:
                    metodologia.nombre = metodologia_data['nombre']
                if 'descripcion' in metodologia_data:
                    metodologia.descripcion = metodologia_data['descripcion']
                
                # Actualizar pasos si vienen
                if 'pasos' in metodologia_data:
                    # Eliminar pasos existentes
                    MetodologiaEventoFraccionPaso.query.filter_by(
                        metodologia_fraccion_id=metodologia.metodologia_fraccion_id
                    ).delete()
                    
                    # Crear nuevos pasos
                    for paso_data in metodologia_data['pasos']:
                        nuevo_paso = MetodologiaEventoFraccionPaso(
                            metodologia_fraccion_id=metodologia.metodologia_fraccion_id,
                            numero_paso=paso_data['numero_paso'],
                            descripcion=paso_data['descripcion']
                        )
                        db.session.add(nuevo_paso)
            else:
                # Crear metodología si no existe
                if not metodologia_data.get('metodologia_fraccion_id'):
                    return jsonify({
                        'success': False,
                        'message': 'metodologia_fraccion_id es requerido'
                    }), 400
                
                nueva_metodologia = MetodologiaEventoFraccion(
                    metodologia_fraccion_id=metodologia_data['metodologia_fraccion_id'],
                    fraccion_evento_id=fraccion_id,
                    nombre=metodologia_data.get('nombre', fraccion.nombre),
                    descripcion=metodologia_data.get('descripcion')
                )
                db.session.add(nueva_metodologia)
                
                # Crear pasos
                for paso_data in metodologia_data.get('pasos', []):
                    nuevo_paso = MetodologiaEventoFraccionPaso(
                        metodologia_fraccion_id=metodologia_data['metodologia_fraccion_id'],
                        numero_paso=paso_data['numero_paso'],
                        descripcion=paso_data['descripcion']
                    )
                    db.session.add(nuevo_paso)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Fracción actualizada exitosamente',
            'data': {
                'fraccion_evento_id': fraccion.fraccion_evento_id,
                'nombre': fraccion.nombre
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al editar fracción: {str(e)}'
        }), 500


# ============================================================================
# 5. ELIMINAR FRACCIÓN
# ============================================================================
@main_bp.route('/api/sop-evento-fracciones/<fraccion_id>', methods=['DELETE'])
def eliminar_fraccion_evento(fraccion_id):
    """
    DELETE /api/sop-evento-fracciones/<fraccion_id>
    
    Elimina una fracción de evento.
    ⚠️ Solo se puede eliminar si NO está siendo usada en ningún SopEvento.
    """
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({
                'success': False,
                'message': 'Fracción no encontrada'
            }), 404
        
        # Verificar si está siendo usada en algún SOP de evento
        if len(fraccion.detalles_sop) > 0:
            return jsonify({
                'success': False,
                'message': 'No se puede eliminar la fracción porque está siendo usada en SOPs de evento',
                'sops_usando': len(fraccion.detalles_sop)
            }), 400
        
        # Eliminar fracción (cascade eliminará metodología y pasos)
        db.session.delete(fraccion)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Fracción eliminada exitosamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al eliminar fracción: {str(e)}'
        }), 500


# ============================================================================
# 1. LISTAR TODOS LOS SOPs DE EVENTO
# ============================================================================
@main_bp.route('/api/sop-eventos', methods=['GET'])
def listar_sop_eventos():
    """
    GET /api/sop-eventos
    
    Retorna todos los SOPs de evento configurados.
    Opcionalmente filtrar por evento_tipo_id o caso_id
    
    Query params:
    - evento_tipo_id: Filtrar por tipo de evento
    - caso_id: Filtrar por caso específico
    """
    try:
        query = SopEvento.query
        
        # Filtros opcionales
        evento_tipo_id = request.args.get('evento_tipo_id')
        caso_id = request.args.get('caso_id')
        
        if evento_tipo_id:
            query = query.filter_by(evento_tipo_id=evento_tipo_id)
        if caso_id:
            query = query.filter_by(caso_id=caso_id)
        
        sop_eventos = query.all()
        
        resultado = []
        for sop_evento in sop_eventos:
            # Calcular tiempo total sumando todas las fracciones
            tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
            
            sop_data = {
                'sop_evento_id': sop_evento.sop_evento_id,
                'evento_tipo_id': sop_evento.evento_tipo_id,
                'evento_nombre': sop_evento.evento_catalogo.nombre,
                'caso_id': sop_evento.caso_id,
                'caso_nombre': sop_evento.caso_catalogo.nombre,
                'nombre': sop_evento.nombre,
                'descripcion': sop_evento.descripcion,
                'total_fracciones': len(sop_evento.detalles),
                'tiempo_total_minutos': tiempo_total
            }
            
            resultado.append(sop_data)
        
        return jsonify({
            'success': True,
            'data': resultado,
            'total': len(resultado)
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al listar SOPs de evento: {str(e)}'
        }), 500


# ============================================================================
# 2. OBTENER DETALLE DE UN SOP DE EVENTO
# ============================================================================
@main_bp.route('/api/sop-eventos/<sop_evento_id>', methods=['GET'])
def obtener_sop_evento(sop_evento_id):
    """
    GET /api/sop-eventos/<sop_evento_id>
    
    Retorna el detalle completo de un SOP de evento con todas sus fracciones configuradas.
    """
    try:
        sop_evento = SopEvento.query.get(sop_evento_id)
        
        if not sop_evento:
            return jsonify({
                'success': False,
                'message': 'SOP de evento no encontrado'
            }), 404
        
        # Construir detalles de fracciones
        fracciones = []
        tiempo_total = 0
        
        for detalle in sop_evento.detalles:
            tiempo_total += detalle.tiempo_estimado
            
            fraccion_data = {
                'detalle_id': detalle.detalle_id,
                'fraccion_evento_id': detalle.fraccion_evento_id,
                'fraccion_nombre': detalle.fraccion.nombre,
                'orden': detalle.orden,
                'tiempo_estimado': detalle.tiempo_estimado,
                'kit_id': detalle.kit_id,
                'kit_nombre': detalle.kit.nombre if detalle.kit else None,
                'receta_id': detalle.receta_id,
                'receta_nombre': detalle.receta.nombre if detalle.receta else None,
                'consumo_id': detalle.consumo_id,
                'consumo_nombre': detalle.consumo.nombre if detalle.consumo else None,
                'observaciones': detalle.observaciones,
                # Incluir pasos de metodología
                'metodologia': {
                    'nombre': detalle.fraccion.metodologia.nombre if detalle.fraccion.metodologia else None,
                    'pasos': [
                        {
                            'numero_paso': paso.numero_paso,
                            'descripcion': paso.descripcion
                        } for paso in detalle.fraccion.metodologia.pasos
                    ] if detalle.fraccion.metodologia else []
                }
            }
            
            fracciones.append(fraccion_data)
        
        sop_data = {
            'sop_evento_id': sop_evento.sop_evento_id,
            'evento_tipo_id': sop_evento.evento_tipo_id,
            'evento_nombre': sop_evento.evento_catalogo.nombre,
            'caso_id': sop_evento.caso_id,
            'caso_nombre': sop_evento.caso_catalogo.nombre,
            'nombre': sop_evento.nombre,
            'descripcion': sop_evento.descripcion,
            'tiempo_total_minutos': tiempo_total,
            'fracciones': fracciones,
            'total_fracciones': len(fracciones)
        }
        
        return jsonify({
            'success': True,
            'data': sop_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener SOP de evento: {str(e)}'
        }), 500


# ============================================================================
# 3. CREAR NUEVO SOP DE EVENTO
# ============================================================================
@main_bp.route('/api/sop-eventos', methods=['POST'])
def crear_sop_evento():
    """
    POST /api/sop-eventos
    
    Crea un nuevo SOP de evento con sus fracciones configuradas.
    
    Body:
    {
        "sop_evento_id": "SE-IN-VO-001",
        "evento_tipo_id": "EV-IN-001",
        "caso_id": "CA-IN-VO-001",
        "nombre": "SOP Incidencia - Vómito",
        "descripcion": "Procedimiento completo para limpieza de vómito",
        "fracciones": [
            {
                "fraccion_evento_id": "FE-SE-001",
                "orden": 1,
                "tiempo_estimado": 3,
                "kit_id": "KT-SE-001",
                "receta_id": null,
                "consumo_id": null,
                "observaciones": "Colocar inmediatamente"
            },
            {
                "fraccion_evento_id": "FE-TR-001",
                "orden": 2,
                "tiempo_estimado": 15,
                "kit_id": "KT-TR-001",
                "receta_id": "RE-DE-001",
                "consumo_id": "CO-VO-001",
                "observaciones": null
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        # Validaciones básicas
        if not data.get('sop_evento_id'):
            return jsonify({'success': False, 'message': 'sop_evento_id es requerido'}), 400
        
        if not data.get('evento_tipo_id'):
            return jsonify({'success': False, 'message': 'evento_tipo_id es requerido'}), 400
        
        if not data.get('caso_id'):
            return jsonify({'success': False, 'message': 'caso_id es requerido'}), 400
        
        if not data.get('nombre'):
            return jsonify({'success': False, 'message': 'nombre es requerido'}), 400
        
        # Verificar que no exista
        if SopEvento.query.get(data['sop_evento_id']):
            return jsonify({'success': False, 'message': 'Ya existe un SOP de evento con ese ID'}), 400
        
        # Verificar que existan evento y caso
        evento = EventoCatalogo.query.get(data['evento_tipo_id'])
        if not evento:
            return jsonify({'success': False, 'message': 'Evento no encontrado'}), 404
        
        caso = CasoCatalogo.query.get(data['caso_id'])
        if not caso:
            return jsonify({'success': False, 'message': 'Caso no encontrado'}), 404
        
        # Verificar que el caso pertenezca al evento
        if caso.evento_tipo_id != data['evento_tipo_id']:
            return jsonify({'success': False, 'message': 'El caso no pertenece a ese tipo de evento'}), 400
        
        # Crear SOP de evento
        nuevo_sop = SopEvento(
            sop_evento_id=data['sop_evento_id'],
            evento_tipo_id=data['evento_tipo_id'],
            caso_id=data['caso_id'],
            nombre=data['nombre'],
            descripcion=data.get('descripcion')
        )
        
        db.session.add(nuevo_sop)
        
        # Crear detalles de fracciones
        fracciones_data = data.get('fracciones', [])
        
        if not fracciones_data:
            return jsonify({'success': False, 'message': 'Debe incluir al menos una fracción'}), 400
        
        for fraccion_data in fracciones_data:
            # Validar que exista la fracción
            fraccion = SopEventoFraccion.query.get(fraccion_data['fraccion_evento_id'])
            if not fraccion:
                return jsonify({
                    'success': False,
                    'message': f"Fracción {fraccion_data['fraccion_evento_id']} no encontrada"
                }), 404
            
            # Validar kit, receta, consumo si vienen
            if fraccion_data.get('kit_id'):
                if not Kit.query.get(fraccion_data['kit_id']):
                    return jsonify({'success': False, 'message': f"Kit {fraccion_data['kit_id']} no encontrado"}), 404
            
            if fraccion_data.get('receta_id'):
                if not Receta.query.get(fraccion_data['receta_id']):
                    return jsonify({'success': False, 'message': f"Receta {fraccion_data['receta_id']} no encontrada"}), 404
            
            if fraccion_data.get('consumo_id'):
                if not Consumo.query.get(fraccion_data['consumo_id']):
                    return jsonify({'success': False, 'message': f"Consumo {fraccion_data['consumo_id']} no encontrado"}), 404
            
            # Crear detalle
            detalle = SopEventoDetalle(
                sop_evento_id=data['sop_evento_id'],
                fraccion_evento_id=fraccion_data['fraccion_evento_id'],
                orden=fraccion_data['orden'],
                tiempo_estimado=fraccion_data['tiempo_estimado'],
                kit_id=fraccion_data.get('kit_id'),
                receta_id=fraccion_data.get('receta_id'),
                consumo_id=fraccion_data.get('consumo_id'),
                observaciones=fraccion_data.get('observaciones')
            )
            
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'SOP de evento creado exitosamente',
            'data': {
                'sop_evento_id': nuevo_sop.sop_evento_id,
                'nombre': nuevo_sop.nombre,
                'total_fracciones': len(fracciones_data)
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al crear SOP de evento: {str(e)}'
        }), 500


# ============================================================================
# 4. EDITAR SOP DE EVENTO
# ============================================================================
@main_bp.route('/api/sop-eventos/<sop_evento_id>', methods=['PUT'])
def editar_sop_evento(sop_evento_id):
    """
    PUT /api/sop-eventos/<sop_evento_id>
    
    Edita un SOP de evento existente.
    Permite actualizar nombre, descripción y fracciones completas.
    
    Body: (mismo formato que POST)
    """
    try:
        sop_evento = SopEvento.query.get(sop_evento_id)
        
        if not sop_evento:
            return jsonify({'success': False, 'message': 'SOP de evento no encontrado'}), 404
        
        data = request.get_json()
        
        # Actualizar campos básicos
        if 'nombre' in data:
            sop_evento.nombre = data['nombre']
        if 'descripcion' in data:
            sop_evento.descripcion = data['descripcion']
        
        # Actualizar fracciones si vienen
        if 'fracciones' in data:
            # Eliminar detalles existentes
            SopEventoDetalle.query.filter_by(sop_evento_id=sop_evento_id).delete()
            
            # Crear nuevos detalles
            for fraccion_data in data['fracciones']:
                # Validaciones (igual que en crear)
                fraccion = SopEventoFraccion.query.get(fraccion_data['fraccion_evento_id'])
                if not fraccion:
                    return jsonify({
                        'success': False,
                        'message': f"Fracción {fraccion_data['fraccion_evento_id']} no encontrada"
                    }), 404
                
                detalle = SopEventoDetalle(
                    sop_evento_id=sop_evento_id,
                    fraccion_evento_id=fraccion_data['fraccion_evento_id'],
                    orden=fraccion_data['orden'],
                    tiempo_estimado=fraccion_data['tiempo_estimado'],
                    kit_id=fraccion_data.get('kit_id'),
                    receta_id=fraccion_data.get('receta_id'),
                    consumo_id=fraccion_data.get('consumo_id'),
                    observaciones=fraccion_data.get('observaciones')
                )
                
                db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'SOP de evento actualizado exitosamente',
            'data': {
                'sop_evento_id': sop_evento.sop_evento_id,
                'nombre': sop_evento.nombre
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al editar SOP de evento: {str(e)}'
        }), 500


# ============================================================================
# 5. ELIMINAR SOP DE EVENTO
# ============================================================================
@main_bp.route('/api/sop-eventos/<sop_evento_id>', methods=['DELETE'])
def eliminar_sop_evento(sop_evento_id):
    """
    DELETE /api/sop-eventos/<sop_evento_id>
    
    Elimina un SOP de evento.
    ⚠️ Solo se puede eliminar si NO tiene lanzamientos asociados.
    """
    try:
        sop_evento = SopEvento.query.get(sop_evento_id)
        
        if not sop_evento:
            return jsonify({'success': False, 'message': 'SOP de evento no encontrado'}), 404
        
        # Verificar si tiene lanzamientos
        if len(sop_evento.lanzamientos) > 0:
            return jsonify({
                'success': False,
                'message': 'No se puede eliminar el SOP porque tiene lanzamientos asociados',
                'lanzamientos_count': len(sop_evento.lanzamientos)
            }), 400
        
        # Eliminar SOP (cascade eliminará los detalles)
        db.session.delete(sop_evento)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'SOP de evento eliminado exitosamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al eliminar SOP de evento: {str(e)}'
        }), 500


# ============================================================================
# 6. OBTENER FRACCIONES DISPONIBLES PARA CONFIGURAR
# ============================================================================
@main_bp.route('/api/sop-eventos/fracciones-disponibles', methods=['GET'])
def obtener_fracciones_disponibles():
    """
    GET /api/sop-eventos/fracciones-disponibles
    
    Retorna todas las fracciones de evento disponibles para configurar un SOP.
    Útil para el selector de fracciones en el frontend.
    """
    try:
        fracciones = SopEventoFraccion.query.all()
        
        resultado = []
        for fraccion in fracciones:
            fraccion_data = {
                'fraccion_evento_id': fraccion.fraccion_evento_id,
                'nombre': fraccion.nombre,
                'descripcion': fraccion.descripcion,
                'tiene_metodologia': fraccion.metodologia is not None,
                'total_pasos': len(fraccion.metodologia.pasos) if fraccion.metodologia else 0
            }
            
            resultado.append(fraccion_data)
        
        return jsonify({
            'success': True,
            'data': resultado,
            'total': len(resultado)
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener fracciones: {str(e)}'
        }), 500



# ============================================================================
# 1. LANZAR EVENTO A OPERADOR
# ============================================================================
@main_bp.route('/api/lanzamiento-evento', methods=['POST'])
def lanzar_evento():
    """
    POST /api/lanzamiento-evento
    
    Lanza un evento a un operador en un día específico.
    
    Body:
    {
        "dia_id": 16,
        "personal_id": "L0212",
        "area_id": "AD-CA-001",
        "subarea_id": "AD-CA-OF-001",
        "sop_evento_id": "SE-IN-VO-001",
        "orden": 100  // opcional, por defecto se coloca al final
    }
    """
    try:
        data = request.get_json()
        
        # Validaciones básicas
        if not data.get('dia_id'):
            return jsonify({'success': False, 'message': 'dia_id es requerido'}), 400
        
        if not data.get('personal_id'):
            return jsonify({'success': False, 'message': 'personal_id es requerido'}), 400
        
        if not data.get('area_id'):
            return jsonify({'success': False, 'message': 'area_id es requerido'}), 400
        
        if not data.get('subarea_id'):
            return jsonify({'success': False, 'message': 'subarea_id es requerido'}), 400
        
        if not data.get('sop_evento_id'):
            return jsonify({'success': False, 'message': 'sop_evento_id es requerido'}), 400
        
        # Verificar que existan los registros
        dia = LanzamientoDia.query.get(data['dia_id'])
        if not dia:
            return jsonify({'success': False, 'message': 'Día no encontrado'}), 404
        
        personal = Personal.query.get(data['personal_id'])
        if not personal:
            return jsonify({'success': False, 'message': 'Personal no encontrado'}), 404
        
        area = Area.query.get(data['area_id'])
        if not area:
            return jsonify({'success': False, 'message': 'Área no encontrada'}), 404
        
        subarea = SubArea.query.get(data['subarea_id'])
        if not subarea:
            return jsonify({'success': False, 'message': 'Subárea no encontrada'}), 404
        
        sop_evento = SopEvento.query.get(data['sop_evento_id'])
        if not sop_evento:
            return jsonify({'success': False, 'message': 'SOP de evento no encontrado'}), 404
        
        # Verificar que la subárea pertenezca al área
        if subarea.area_id != data['area_id']:
            return jsonify({'success': False, 'message': 'La subárea no pertenece a esa área'}), 400
        
        # Determinar orden (si no viene, colocar al final)
        orden = data.get('orden')
        if orden is None:
            # Obtener el orden máximo actual para ese día/personal
            max_orden = db.session.query(db.func.max(LanzamientoTarea.orden))\
                .filter_by(dia_id=data['dia_id'], personal_id=data['personal_id'])\
                .scalar() or 0
            orden = max_orden + 1
        
        # Crear lanzamiento de tarea
        nueva_tarea = LanzamientoTarea(
            dia_id=data['dia_id'],
            personal_id=data['personal_id'],
            area_id=data['area_id'],
            subarea_id=data['subarea_id'],
            sop_evento_id=data['sop_evento_id'],
            tipo_tarea='evento',
            orden=orden,
            es_adicional=data.get('es_adicional', False),
            es_arrastrable=False  # Los eventos NO son arrastrables
        )
        
        db.session.add(nueva_tarea)
        asegurar_tareas_fijas(data['dia_id'], data['personal_id'])
        db.session.commit()
        
        # Calcular tiempo total del evento
        tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
        
        return jsonify({
            'success': True,
            'message': 'Evento lanzado exitosamente',
            'data': {
                'tarea_id': nueva_tarea.tarea_id,
                'personal_nombre': personal.nombre,
                'area_nombre': area.nombre,
                'subarea_nombre': subarea.nombre,
                'evento_nombre': sop_evento.evento_catalogo.nombre,
                'caso_nombre': sop_evento.caso_catalogo.nombre,
                'sop_evento_nombre': sop_evento.nombre,
                'tiempo_estimado_minutos': tiempo_total,
                'total_fracciones': len(sop_evento.detalles)
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al lanzar evento: {str(e)}'
        }), 500


# ============================================================================
# 2. OBTENER EVENTOS ASIGNADOS A UN OPERADOR
# ============================================================================
@main_bp.route('/api/operador/<personal_id>/eventos', methods=['GET'])
def obtener_eventos_operador(personal_id):
    """
    GET /api/operador/<personal_id>/eventos
    
    Retorna todos los eventos asignados a un operador.
    
    Query params:
    - dia_id: Filtrar por día específico
    - completado: Filtrar por completado (true/false)
    """
    try:
        query = LanzamientoTarea.query.filter_by(
            personal_id=personal_id,
            tipo_tarea='evento'
        )
        
        # Filtros opcionales
        dia_id = request.args.get('dia_id')
        completado = request.args.get('completado')
        
        if dia_id:
            query = query.filter_by(dia_id=int(dia_id))
        
        tareas = query.order_by(LanzamientoTarea.orden).all()
        
        # Filtrar por completado si viene el parámetro
        if completado is not None:
            completado_bool = completado.lower() == 'true'
            tareas = [t for t in tareas if (t.check is not None) == completado_bool]
        
        resultado = []
        for tarea in tareas:
            sop_evento = tarea.sop_evento
            tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
            
            tarea_data = {
                'tarea_id': tarea.tarea_id,
                'dia_id': tarea.dia_id,
                'fecha': tarea.dia.fecha.isoformat(),
                'area_id': tarea.area_id,
                'area_nombre': tarea.area.nombre,
                'subarea_id': tarea.subarea_id,
                'subarea_nombre': tarea.subarea.nombre,
                'sop_evento_id': tarea.sop_evento_id,
                'evento_nombre': sop_evento.evento_catalogo.nombre,
                'caso_nombre': sop_evento.caso_catalogo.nombre,
                'sop_evento_nombre': sop_evento.nombre,
                'tiempo_estimado_minutos': tiempo_total,
                'total_fracciones': len(sop_evento.detalles),
                'orden': tarea.orden,
                'completado': tarea.check is not None,
                'fecha_completado': tarea.check.checked_at.isoformat() if tarea.check else None,
                'completado_por': tarea.check.user_id if tarea.check else None
            }
            
            resultado.append(tarea_data)
        
        return jsonify({
            'success': True,
            'data': resultado,
            'total': len(resultado),
            'completados': sum(1 for t in resultado if t['completado']),
            'pendientes': sum(1 for t in resultado if not t['completado'])
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener eventos: {str(e)}'
        }), 500


# ============================================================================
# 3. OBTENER DETALLE DE EVENTO PARA EJECUCIÓN
# ============================================================================
@main_bp.route('/api/evento-ejecucion/<tarea_id>', methods=['GET'])
def obtener_evento_ejecucion(tarea_id):
    """
    GET /api/evento-ejecucion/<tarea_id>
    
    Retorna el detalle completo del evento para que el operador lo ejecute.
    Incluye todas las fracciones con sus metodologías, pasos, kits, etc.
    """
    try:
        tarea = LanzamientoTarea.query.get(tarea_id)
        
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'}), 404
        
        if tarea.tipo_tarea != 'evento':
            return jsonify({'success': False, 'message': 'Esta tarea no es un evento'}), 400
        
        sop_evento = tarea.sop_evento
        
        # Construir fracciones con todos los detalles
        fracciones = []
        tiempo_total = 0
        
        for detalle in sop_evento.detalles:
            tiempo_total += detalle.tiempo_estimado
            
            # ✅ Obtener pasos de metodología CON título de la fracción
            pasos = []
            if detalle.fraccion.metodologia:
                for paso in detalle.fraccion.metodologia.pasos:
                    pasos.append({
                        'numero_paso': paso.numero_paso,
                        'titulo': detalle.fraccion.nombre,  # ← AGREGADO: título viene de la fracción
                        'descripcion': paso.descripcion
                    })
            
            fraccion_data = {
                'detalle_id': detalle.detalle_id,
                'fraccion_evento_id': detalle.fraccion_evento_id,
                'fraccion_nombre': detalle.fraccion.nombre,
                'fraccion_descripcion': detalle.fraccion.descripcion,
                'orden': detalle.orden,
                'tiempo_estimado': detalle.tiempo_estimado,
                'observaciones': detalle.observaciones,
                # Kit
                'kit': {
                    'kit_id': detalle.kit_id,
                    'nombre': detalle.kit.nombre if detalle.kit else None,
                    'descripcion': detalle.kit.descripcion if detalle.kit else None
                } if detalle.kit_id else None,
                # Receta
                'receta': {
                    'receta_id': detalle.receta_id,
                    'nombre': detalle.receta.nombre if detalle.receta else None,
                    'descripcion': detalle.receta.descripcion if detalle.receta else None
                } if detalle.receta_id else None,
                # Consumo
                'consumo': {
                    'consumo_id': detalle.consumo_id,
                    'nombre': detalle.consumo.nombre if detalle.consumo else None,
                    'descripcion': detalle.consumo.descripcion if detalle.consumo else None
                } if detalle.consumo_id else None,
                # Metodología con pasos
                'metodologia': {
                    'nombre': detalle.fraccion.metodologia.nombre if detalle.fraccion.metodologia else None,
                    'descripcion': detalle.fraccion.metodologia.descripcion if detalle.fraccion.metodologia else None,
                    'pasos': pasos
                }
            }
            
            fracciones.append(fraccion_data)
        
        evento_data = {
            'tarea_id': tarea.tarea_id,
            'area_nombre': tarea.area.nombre,
            'subarea_nombre': tarea.subarea.nombre,
            'evento_tipo': sop_evento.evento_catalogo.nombre,
            'caso': sop_evento.caso_catalogo.nombre,
            'sop_nombre': sop_evento.nombre,
            'sop_descripcion': sop_evento.descripcion,
            'tiempo_total_minutos': tiempo_total,
            'fracciones': fracciones,
            'total_fracciones': len(fracciones),
            'completado': tarea.check is not None,
            'fecha_completado': tarea.check.checked_at.isoformat() if tarea.check else None
        }
        
        return jsonify({
            'success': True,
            'data': evento_data
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener evento: {str(e)}'
        }), 500


# ============================================================================
# 4. MARCAR EVENTO COMO COMPLETADO
# ============================================================================
@main_bp.route('/api/evento-completar/<tarea_id>', methods=['POST'])
def completar_evento(tarea_id):
    """
    POST /api/evento-completar/<tarea_id>
    
    Marca un evento como completado por el operador.
    
    Body:
    {
        "user_id": 1  // ID del usuario que completa (puede ser el operador o supervisor)
    }
    """
    try:
        tarea = LanzamientoTarea.query.get(tarea_id)
        
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'}), 404
        
        if tarea.tipo_tarea != 'evento':
            return jsonify({'success': False, 'message': 'Esta tarea no es un evento'}), 400
        
        # Verificar si ya está completado
        if tarea.check:
            return jsonify({
                'success': False,
                'message': 'Este evento ya está completado',
                'fecha_completado': tarea.check.checked_at.isoformat()
            }), 400
        
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'user_id es requerido'}), 400
        
        # Crear check
        nuevo_check = TareaCheck(
            tarea_id=tarea_id,
            checked_at=datetime.utcnow(),
            user_id=user_id
        )
        
        db.session.add(nuevo_check)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Evento completado exitosamente',
            'data': {
                'tarea_id': tarea_id,
                'check_id': nuevo_check.check_id,
                'checked_at': nuevo_check.checked_at.isoformat(),
                'user_id': user_id
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al completar evento: {str(e)}'
        }), 500


# ============================================================================
# 5. CANCELAR/ELIMINAR EVENTO ASIGNADO
# ============================================================================
@main_bp.route('/api/evento-cancelar/<tarea_id>', methods=['DELETE'])
def cancelar_evento(tarea_id):
    """
    DELETE /api/evento-cancelar/<tarea_id>
    
    Cancela/elimina un evento asignado.
    Solo se puede cancelar si NO está completado.
    """
    try:
        tarea = LanzamientoTarea.query.get(tarea_id)
        
        if not tarea:
            return jsonify({'success': False, 'message': 'Tarea no encontrada'}), 404
        
        if tarea.tipo_tarea != 'evento':
            return jsonify({'success': False, 'message': 'Esta tarea no es un evento'}), 400
        
        # Verificar si está completado
        if tarea.check:
            return jsonify({
                'success': False,
                'message': 'No se puede cancelar un evento completado'
            }), 400
        
        # Eliminar tarea (cascade eliminará el check si existiera)
        db.session.delete(tarea)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Evento cancelado exitosamente'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al cancelar evento: {str(e)}'
        }), 500


# ============================================================================
# 6. OBTENER EVENTOS POR DÍA (PARA SUPERVISOR)
# ============================================================================
@main_bp.route('/api/eventos-dia/<int:dia_id>', methods=['GET'])
def obtener_eventos_dia(dia_id):
    """
    GET /api/eventos-dia/<dia_id>
    
    Retorna todos los eventos lanzados en un día específico.
    Útil para vista de supervisor.
    
    Query params:
    - area_id: Filtrar por área
    - completado: Filtrar por estado (true/false)
    """
    try:
        query = LanzamientoTarea.query.filter_by(
            dia_id=dia_id,
            tipo_tarea='evento'
        )
        
        # Filtros opcionales
        area_id = request.args.get('area_id')
        completado = request.args.get('completado')
        
        if area_id:
            query = query.filter_by(area_id=area_id)
        
        tareas = query.order_by(LanzamientoTarea.personal_id, LanzamientoTarea.orden).all()
        
        # Filtrar por completado si viene el parámetro
        if completado is not None:
            completado_bool = completado.lower() == 'true'
            tareas = [t for t in tareas if (t.check is not None) == completado_bool]
        
        resultado = []
        for tarea in tareas:
            sop_evento = tarea.sop_evento
            tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)
            
            tarea_data = {
                'tarea_id': tarea.tarea_id,
                'personal_id': tarea.personal_id,
                'personal_nombre': tarea.personal.nombre,
                'area_id': tarea.area_id,
                'area_nombre': tarea.area.nombre,
                'subarea_id': tarea.subarea_id,
                'subarea_nombre': tarea.subarea.nombre,
                'evento_tipo': sop_evento.evento_catalogo.nombre,
                'caso': sop_evento.caso_catalogo.nombre,
                'sop_evento_nombre': sop_evento.nombre,
                'tiempo_estimado_minutos': tiempo_total,
                'orden': tarea.orden,
                'completado': tarea.check is not None,
                'fecha_completado': tarea.check.checked_at.isoformat() if tarea.check else None
            }
            
            resultado.append(tarea_data)
        
        return jsonify({
            'success': True,
            'data': resultado,
            'total': len(resultado),
            'completados': sum(1 for t in resultado if t['completado']),
            'pendientes': sum(1 for t in resultado if not t['completado'])
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener eventos del día: {str(e)}'
        }), 500
    

# ============================================================================
# 1. CREAR/SELECCIONAR FRACCIONES (TODO EN UNO)
# ============================================================================
@main_bp.route('/sop-evento-crear', methods=['GET', 'POST'])
@admin_required
def sop_evento_crear():
    """
    Crea el SOP de evento (si no existe) y permite seleccionar fracciones.
    Equivalente a sop_crear de regular.
    ID es determinístico 1:1 por evento-caso.
    """
    evento_tipo_id = request.args.get('evento_tipo_id') or request.form.get('evento_tipo_id')
    caso_id = request.args.get('caso_id') or request.form.get('caso_id')
    
    if not evento_tipo_id or not caso_id:
        flash('Debe seleccionar tipo de evento y caso', 'error')
        return redirect(url_for('main.sop_panel'))
    
    # Verificar que existan
    evento = EventoCatalogo.query.get(evento_tipo_id)
    caso = CasoCatalogo.query.get(caso_id)
    
    if not evento or not caso:
        flash('Evento o caso no encontrado', 'error')
        return redirect(url_for('main.sop_panel'))
    
    # Extraer códigos cortos: CA-IN-VO-001 → IN, VO
    partes = caso_id.split('-')
    if len(partes) >= 3:
        tipo_corto = partes[1]  # IN
        caso_corto = partes[2]  # VO
    else:
        flash('Formato de caso_id inválido', 'error')
        return redirect(url_for('main.sop_panel'))
    
    # ✅ Generar ID determinístico (siempre el mismo para este evento-caso)
    sop_evento_id = f"SP-{tipo_corto}-{caso_corto}-001"
    
    # ✅ Buscar SOP existente por ID
    sop_evento = SopEvento.query.get(sop_evento_id)
    
    # Obtener fracciones disponibles para este tipo de evento
    fracciones = (
        SopEventoFraccion.query
        .filter_by(evento_tipo_id=evento_tipo_id)
        .order_by(SopEventoFraccion.fraccion_evento_id.asc())
        .all()
    )
    
    # Obtener fracciones ya seleccionadas (si el SOP existe)
    selected_ids = set()
    orden_map = {}
    
    if sop_evento and sop_evento.detalles:
        selected_ids = {d.fraccion_evento_id for d in sop_evento.detalles}
        orden_map = {d.fraccion_evento_id: d.orden for d in sop_evento.detalles}
    
    # POST: guardar selección
    if request.method == "POST":
        selected = request.form.getlist("fraccion_evento_id")
        selected_set = set(selected)
        
        if not selected:
            flash("Selecciona al menos 1 fracción", "warning")
            return redirect(url_for("main.sop_evento_crear", 
                                   evento_tipo_id=evento_tipo_id,
                                   caso_id=caso_id))
        
        # 1) Crear SOP si no existe
        if not sop_evento:
            sop_evento = SopEvento(
                sop_evento_id=sop_evento_id,
                evento_tipo_id=evento_tipo_id,
                caso_id=caso_id,
                nombre=f"SOP {evento.nombre} - {caso.nombre}",
                descripcion=f"SOP para {caso.nombre}"
            )
            db.session.add(sop_evento)
            db.session.flush()
        
        # 2) Eliminar fracciones que ya no están seleccionadas
        prev_selected = selected_ids.copy() if selected_ids else set()
        to_remove = prev_selected - selected_set
        
        if to_remove:
            SopEventoDetalle.query.filter(
                SopEventoDetalle.sop_evento_id == sop_evento_id,
                SopEventoDetalle.fraccion_evento_id.in_(list(to_remove))
            ).delete(synchronize_session=False)
        
        # 3) Crear o actualizar fracciones seleccionadas
        for fraccion_id in selected:
            orden_raw = (request.form.get(f"orden_{fraccion_id}") or "").strip()
            orden = int(orden_raw) if orden_raw.isdigit() else 1000
            
            detalle = SopEventoDetalle.query.filter_by(
                sop_evento_id=sop_evento_id,
                fraccion_evento_id=fraccion_id
            ).first()
            
            if detalle:
                # Actualizar orden
                detalle.orden = orden
            else:
                # Crear nuevo
                nuevo_detalle = SopEventoDetalle(
                    sop_evento_id=sop_evento_id,
                    fraccion_evento_id=fraccion_id,
                    orden=orden,
                    tiempo_estimado=15  # Default 15 minutos
                )
                db.session.add(nuevo_detalle)
        
        db.session.commit()
        flash("✅ Fracciones guardadas exitosamente", "success")
        
        # Redirigir a editar fracciones (equivalente a sop_fracciones_edit)
        return redirect(url_for("main.sop_evento_editar", 
                               sop_evento_id=sop_evento_id))
    
    # GET: mostrar form
    return render_template(
        "sop_evento_crear.html",
        sop_evento=sop_evento,
        sop_evento_id=sop_evento_id,
        evento=evento,
        caso=caso,
        fracciones=fracciones,
        selected_ids=selected_ids,
        orden_map=orden_map
    )

# ============================================================================
# 2. EDITAR SOP EVENTO (decide si ir a crear o a detalles)
# ============================================================================
@main_bp.route("/sop-evento/<sop_evento_id>/editar")
@admin_required
def sop_evento_editar(sop_evento_id):
    """
    Punto de entrada para editar un SOP de evento.
    Equivalente a sop_fracciones_edit de regular.
    
    - Si NO tiene fracciones → redirige a sop_evento_crear
    - Si YA tiene fracciones → redirige a sop_evento_detalle (primera)
    """
    sop_evento = SopEvento.query.get_or_404(sop_evento_id)
    
    # Verificar si tiene fracciones
    tiene_fracciones = (
        db.session.query(SopEventoDetalle.detalle_id)
        .filter_by(sop_evento_id=sop_evento_id)
        .first()
        is not None
    )
    
    if not tiene_fracciones:
        # No tiene fracciones → ir a seleccionar
        return redirect(url_for("main.sop_evento_crear",
                               evento_tipo_id=sop_evento.evento_tipo_id,
                               caso_id=sop_evento.caso_id))
    
    # Ya tiene fracciones → ir a editar la primera
    primer_detalle = (
        SopEventoDetalle.query
        .filter_by(sop_evento_id=sop_evento_id)
        .order_by(SopEventoDetalle.orden.asc())
        .first()
    )
    
    return redirect(url_for("main.sop_evento_detalle",
                           sop_evento_id=sop_evento_id,
                           detalle_id=primer_detalle.detalle_id))


@main_bp.route("/sop-evento/<sop_evento_id>/detalle", methods=["GET", "POST"])
@admin_required
def sop_evento_detalle(sop_evento_id):
    """
    Edita fracción por fracción de un SOP de evento.
    Equivalente a sop_detalles pero SIN niveles y SIN elementos.
    Solo: Kit, Receta, Consumo, Tiempo.
    """
    sop_evento = SopEvento.query.get_or_404(sop_evento_id)
    
    # POST: Guardar cambios PRIMERO (antes de cargar detalles_list)
    if request.method == "POST":
        detalle_id = request.form.get("detalle_id", "").strip()
        
        if not detalle_id:
            flash("Detalle ID no encontrado", "error")
            return redirect(url_for("main.sop_evento_detalle",
                                   sop_evento_id=sop_evento_id))
        
        # Obtener el detalle específico para editar
        detalle_actual = SopEventoDetalle.query.get(int(detalle_id))
        
        if not detalle_actual or detalle_actual.sop_evento_id != sop_evento_id:
            flash("Detalle no encontrado", "error")
            return redirect(url_for("main.sop_evento_detalle",
                                   sop_evento_id=sop_evento_id))
        
        # Tiempo estimado
        tiempo_raw = request.form.get("tiempo_estimado", "").strip()
        if tiempo_raw:
            try:
                detalle_actual.tiempo_estimado = int(tiempo_raw)
            except ValueError:
                flash("Tiempo inválido", "warning")
                return redirect(url_for("main.sop_evento_detalle",
                                       sop_evento_id=sop_evento_id,
                                       detalle_id=detalle_actual.detalle_id))
        
        # Kit, Receta, Consumo
        detalle_actual.kit_id = request.form.get("kit_id", "").strip() or None
        detalle_actual.receta_id = request.form.get("receta_id", "").strip() or None
        detalle_actual.consumo_id = request.form.get("consumo_id", "").strip() or None
        
        try:
            db.session.commit()
            flash("✅ Detalle guardado", "success")
        except Exception as e:
            db.session.rollback()
            print("💥 ERROR guardando detalle evento:", repr(e))
            flash("Error guardando detalle", "error")
        
        return redirect(url_for("main.sop_evento_detalle",
                               sop_evento_id=sop_evento_id,
                               detalle_id=detalle_actual.detalle_id))
    
    # GET: Cargar datos para mostrar
    # Obtener TODOS los detalles del SOP (fracciones asignadas)
    detalles_list = (
        SopEventoDetalle.query
        .filter_by(sop_evento_id=sop_evento_id)
        .order_by(SopEventoDetalle.orden.asc())
        .all()
    )
    
    if not detalles_list:
        flash("Este SOP no tiene fracciones todavía", "warning")
        return redirect(url_for("main.sop_panel",
                               evento_tipo_id=sop_evento.evento_tipo_id,
                               caso_id=sop_evento.caso_id))
    
    # Determinar qué detalle estamos mostrando
    detalle_id = request.args.get("detalle_id", "").strip()
    
    if detalle_id:
        detalle_id = int(detalle_id)
        detalle_actual = next((d for d in detalles_list if d.detalle_id == detalle_id), 
                             detalles_list[0])
    else:
        detalle_actual = detalles_list[0]
    
    # ✅ Filtrar kits por tipo_kit='evento' Y caso_id del SOP
    kits = (
        Kit.query
        .filter_by(tipo_kit='evento', caso_id=sop_evento.caso_id)
        .order_by(Kit.nombre.asc())
        .all()
    )
    
    recetas = Receta.query.order_by(Receta.receta_id.asc()).all()
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
    
    # Metodología de la fracción (solo lectura)
    metodologia = None
    if detalle_actual.fraccion.metodologia:
        metodologia = detalle_actual.fraccion.metodologia
    
    # GET: Renderizar
    return render_template(
        "sop_evento_detalle.html",
        sop_evento=sop_evento,
        detalles_list=detalles_list,
        detalle_actual=detalle_actual,
        kits=kits,
        recetas=recetas,
        consumos=consumos,
        metodologia=metodologia,
        hide_nav=True
    )

# =========================
# CATÁLOGOS - QUÍMICOS Y RECETAS
# =========================
@main_bp.route("/catalogos/quimicos-recetas")
@admin_required
def catalogos_quimicos_recetas():
    """
    Panel unificado para gestionar Químicos y Recetas
    Usa tabs para cambiar entre ambas vistas
    """
    import json
    from decimal import Decimal
    
    # Obtener todos los químicos ordenados
    quimicos = Quimico.query.order_by(Quimico.nombre.asc()).all()
    
    # Obtener todas las recetas con sus detalles
    recetas = (
        Receta.query
        .options(joinedload(Receta.detalles).joinedload(RecetaDetalle.quimico))
        .order_by(Receta.nombre.asc())
        .all()
    )
    
    # ✅ SERIALIZAR RECETAS A JSON STRING (no dict)
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
    
    # ✅ Convertir a JSON string en Python (siempre devuelve algo válido)
    recetas_json_str = json.dumps(recetas_list, ensure_ascii=False) if recetas_list else '[]'
    
    return render_template(
        "catalogos/compartidos/quimicos_recetas.html",
        quimicos=quimicos,
        recetas=recetas,
        recetas_json_str=recetas_json_str  # ✅ Ya es un string JSON válido
    )

# =========================
# API - QUÍMICOS (CRUD)
# =========================

@main_bp.route("/api/quimicos/catalogos", methods=["GET"])
@admin_required
def api_quimicos_catalogos():
    """
    Obtiene los catálogos dinámicos para crear/editar químicos:
    - Grupos disponibles (código + nombre de categoría)
    - Presentaciones existentes
    - Unidades base existentes
    """
    try:
        GLOSARIO_QUIMICOS = {
            'AA': 'ACABADO',
            'AB': 'ABRASIVO',
            'AC': 'ACIDO',
            'DE': 'DETERGENTE',
            'DN': 'DESENGRASANTE',
            'DS': 'DESINFECTANTE',
            'LI': 'LIMPIADOR',
            'SA': 'SANITIZANTE',
            'SU': 'SUPRESOR',
        }

        # Crear lista para el frontend (mantiene formato del dropdown)
        grupos = [
            {"codigo": codigo, "nombre": categoria}
            for codigo, categoria in sorted(GLOSARIO_QUIMICOS.items())
        ]
        
        # Extraer presentaciones existentes
        presentaciones_raw = db.session.query(
            Quimico.presentacion
        ).filter(
            Quimico.presentacion.isnot(None),
            Quimico.presentacion != ''
        ).distinct().all()
        
        presentaciones = sorted([p[0] for p in presentaciones_raw if p[0]])
        
        # Extraer unidades base existentes
        unidades_raw = db.session.query(
            Quimico.unidad_base
        ).filter(
            Quimico.unidad_base.isnot(None),
            Quimico.unidad_base != ''
        ).distinct().all()
        
        unidades = sorted([u[0] for u in unidades_raw if u[0]])
        
        return jsonify({
            "success": True,
            "grupos": grupos,
            "presentaciones": presentaciones,
            "unidades": unidades
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/quimicos/next-id", methods=["GET"])
@admin_required
def api_quimicos_next_id():
    """
    Genera el próximo ID disponible para un grupo específico.
    Query param: grupo (ej: DS, AC, SU)
    Retorna: QU-{grupo}-{número} (ej: QU-DS-003)
    """
    grupo = request.args.get("grupo", "").strip().upper()
    
    if not grupo:
        return jsonify({"success": False, "error": "Grupo requerido"}), 400
    
    if len(grupo) != 2:
        return jsonify({"success": False, "error": "Grupo debe tener 2 caracteres"}), 400
    
    try:
        # Buscar el último químico de este grupo
        # Pattern: QU-{grupo}-%
        pattern = f"QU-{grupo}-%"
        ultimo = Quimico.query.filter(
            Quimico.quimico_id.like(pattern)
        ).order_by(
            Quimico.quimico_id.desc()
        ).first()
        
        if ultimo:
            # Extraer el número del ID (ej: "QU-DS-004" → "004" → 4)
            partes = ultimo.quimico_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            # Primer químico de este grupo
            siguiente = 1
        
        # Formatear con 3 dígitos (001, 002, ..., 999)
        nuevo_id = f"QU-{grupo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "quimico_id": nuevo_id,
            "grupo": grupo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/quimicos", methods=["POST"])
@admin_required
def api_quimicos_crear():
    """
    Crea un nuevo químico.
    Body JSON:
    {
        "grupo": "DS",
        "nombre": "Alpha HP",
        "presentacion": "Liquido",  // opcional
        "unidad_base": "mL"         // opcional
    }
    """
    try:
        data = request.get_json()
        
        # Validaciones
        grupo = data.get("grupo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        presentacion = data.get("presentacion", "").strip() or None
        unidad_base = data.get("unidad_base", "").strip() or None
        
        if not grupo or len(grupo) != 2:
            return jsonify({"success": False, "error": "Grupo inválido (2 caracteres)"}), 400
        
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # Validar nombre único
        existe_nombre = Quimico.query.filter(
            db.func.upper(Quimico.nombre) == nombre.upper()
        ).first()
        
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe un químico con el nombre '{nombre}'"
            }), 400
        
        # Generar ID
        pattern = f"QU-{grupo}-%"
        ultimo = Quimico.query.filter(
            Quimico.quimico_id.like(pattern)
        ).order_by(
            Quimico.quimico_id.desc()
        ).first()
        
        if ultimo:
            partes = ultimo.quimico_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        quimico_id = f"QU-{grupo}-{siguiente:03d}"
        
        # Obtener categoría del grupo (buscar en químicos existentes)
        categoria_ref = Quimico.query.filter(
            Quimico.quimico_id.like(pattern)
        ).first()
        
        if categoria_ref:
            categoria = categoria_ref.categoria
        else:
            # Si es un grupo nuevo, usar el código como categoría temporal
            categoria = grupo
        
        # Crear químico
        nuevo_quimico = Quimico(
            quimico_id=quimico_id,
            nombre=nombre,
            categoria=categoria,
            presentacion=presentacion,
            unidad_base=unidad_base
        )
        
        db.session.add(nuevo_quimico)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "quimico": {
                "quimico_id": nuevo_quimico.quimico_id,
                "nombre": nuevo_quimico.nombre,
                "categoria": nuevo_quimico.categoria,
                "presentacion": nuevo_quimico.presentacion,
                "unidad_base": nuevo_quimico.unidad_base
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/quimicos/<quimico_id>", methods=["PUT"])
@admin_required
def api_quimicos_editar(quimico_id):
    """
    Edita un químico existente.
    Solo permite editar: nombre, presentacion, unidad_base
    NO permite editar: quimico_id, categoria (viene del grupo)
    
    Body JSON:
    {
        "nombre": "Nuevo Nombre",
        "presentacion": "Botella 1L",  // opcional
        "unidad_base": "L"              // opcional
    }
    """
    try:
        quimico = Quimico.query.get(quimico_id)
        
        if not quimico:
            return jsonify({"success": False, "error": "Químico no encontrado"}), 404
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_presentacion = data.get("presentacion", "").strip() or None
        nueva_unidad = data.get("unidad_base", "").strip() or None
        
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # Validar nombre único (excluyendo el actual)
        existe_nombre = Quimico.query.filter(
            db.func.upper(Quimico.nombre) == nuevo_nombre.upper(),
            Quimico.quimico_id != quimico_id
        ).first()
        
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe otro químico con el nombre '{nuevo_nombre}'"
            }), 400
        
        # Actualizar
        quimico.nombre = nuevo_nombre
        quimico.presentacion = nueva_presentacion
        quimico.unidad_base = nueva_unidad
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "quimico": {
                "quimico_id": quimico.quimico_id,
                "nombre": quimico.nombre,
                "categoria": quimico.categoria,
                "presentacion": quimico.presentacion,
                "unidad_base": quimico.unidad_base
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/quimicos/<quimico_id>", methods=["DELETE"])
@admin_required
def api_quimicos_eliminar(quimico_id):
    """
    Elimina un químico.
    Valida que NO esté siendo usado en ninguna receta.
    """
    try:
        quimico = Quimico.query.get(quimico_id)
        
        if not quimico:
            return jsonify({"success": False, "error": "Químico no encontrado"}), 404
        
        # Validar que no esté en recetas
        en_recetas = RecetaDetalle.query.filter_by(quimico_id=quimico_id).count()
        
        if en_recetas > 0:
            # Obtener nombres de recetas donde está usado
            recetas_nombres = db.session.query(Receta.nombre).join(
                RecetaDetalle
            ).filter(
                RecetaDetalle.quimico_id == quimico_id
            ).distinct().all()
            
            nombres = [r[0] for r in recetas_nombres]
            
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Este químico está en {en_recetas} receta(s)",
                "recetas": nombres
            }), 400
        
        # Eliminar
        db.session.delete(quimico)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Químico {quimico_id} eliminado correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

# =========================
# API - RECETAS (CRUD)
# =========================

@main_bp.route("/api/recetas/catalogos", methods=["GET"])
@admin_required
def api_recetas_catalogos():
    """
    Obtiene los químicos disponibles para crear/editar recetas.
    Retorna lista de químicos ordenados por ID.
    """
    try:
        quimicos = Quimico.query.order_by(Quimico.quimico_id.asc()).all()
        
        quimicos_list = [
            {
                "quimico_id": q.quimico_id,
                "nombre": q.nombre,
                "categoria": q.categoria,
                "presentacion": q.presentacion,
                "unidad_base": q.unidad_base
            }
            for q in quimicos
        ]
        
        return jsonify({
            "success": True,
            "quimicos": quimicos_list
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/recetas/next-id", methods=["GET"])
@admin_required
def api_recetas_next_id():
    """
    Genera el próximo ID disponible para un código específico.
    Query param: codigo (ej: BA, TL, TRA)
    Retorna: RE-{codigo}-{número} (ej: RE-BA-003)
    """
    codigo = request.args.get("codigo", "").strip().upper()
    
    if not codigo:
        return jsonify({"success": False, "error": "Código requerido"}), 400
    

    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Código debe tener exactamente 2 caracteres"}), 400
    
    try:
        # Buscar la última receta de este código
        # Pattern: RE-{codigo}-%
        pattern = f"RE-{codigo}-%"
        ultima = Receta.query.filter(
            Receta.receta_id.like(pattern)
        ).order_by(
            Receta.receta_id.desc()
        ).first()
        
        if ultima:
            # Extraer el número del ID (ej: "RE-BA-004" → "004" → 4)
            partes = ultima.receta_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            # Primera receta de este código
            siguiente = 1
        
        # Formatear con 3 dígitos (001, 002, ..., 999)
        nuevo_id = f"RE-{codigo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "receta_id": nuevo_id,
            "codigo": codigo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/recetas", methods=["POST"])
@admin_required
def api_recetas_crear():
    """
    Crea una nueva receta con su detalle.
    Body JSON:
    {
        "codigo": "BA",
        "nombre": "Tallar Baños",
        "quimico_id": "QU-AC-001",
        "dosis": 25,
        "volumen_base": 1000
    }
    
    Crea:
    - Receta (receta_id, nombre)
    - RecetaDetalle (receta_id, quimico_id, dosis, unidad_dosis=mL, volumen_base, unidad_volumen=mL, nota=nombre)
    """
    try:
        data = request.get_json()
        
        # Validaciones
        codigo = data.get("codigo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        quimico_id = data.get("quimico_id", "").strip()
        dosis = data.get("dosis")
        volumen_base = data.get("volumen_base")

        # 1. Validar formato de código
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Código inválido"}), 400

        # 2. Validar que código venga de fracción existente  
        pattern_fraccion = f"FR-{codigo}-%"
        fraccion_existe = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern_fraccion)
        ).first()

        if not fraccion_existe:
            return jsonify({
                "success": False, 
                "error": f"El código '{codigo}' no corresponde a ninguna fracción existente"
            }), 400

        # 3. Validar campos básicos
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400

        if not quimico_id:
            return jsonify({"success": False, "error": "Químico requerido"}), 400

        if dosis is None or dosis < 0:
            return jsonify({"success": False, "error": "Dosis debe ser 0 o mayor"}), 400

        if volumen_base is None or volumen_base < 0:
            return jsonify({"success": False, "error": "Volumen base debe ser 0 o mayor"}), 400

        # 4. Validar nombre único (hace query a BD)
        existe_nombre = Receta.query.filter(
            db.func.upper(Receta.nombre) == nombre.upper()
        ).first()

        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe una receta con el nombre '{nombre}'"
            }), 400

        # 5. Validar que el químico existe (hace query a BD)
        quimico = Quimico.query.get(quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Químico no encontrado"}), 404
        
        # Generar ID
        pattern = f"RE-{codigo}-%"
        ultima = Receta.query.filter(
            Receta.receta_id.like(pattern)
        ).order_by(
            Receta.receta_id.desc()
        ).first()
        
        if ultima:
            partes = ultima.receta_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        receta_id = f"RE-{codigo}-{siguiente:03d}"
        
        # Crear Receta
        nueva_receta = Receta(
            receta_id=receta_id,
            nombre=nombre
        )
        db.session.add(nueva_receta)
        db.session.flush()  # Para obtener el ID antes del commit
        
        # Crear RecetaDetalle
        detalle = RecetaDetalle(
            receta_id=receta_id,
            quimico_id=quimico_id,
            dosis=dosis,
            unidad_dosis="mL",  # Fijo
            volumen_base=volumen_base,
            unidad_volumen="mL",  # Fijo
            nota=nombre  # ✅ Mismo valor que el nombre
        )
        db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "receta": {
                "receta_id": nueva_receta.receta_id,
                "nombre": nueva_receta.nombre,
                "detalle": {
                    "quimico_id": detalle.quimico_id,
                    "dosis": detalle.dosis,
                    "unidad_dosis": detalle.unidad_dosis,
                    "volumen_base": detalle.volumen_base,
                    "unidad_volumen": detalle.unidad_volumen,
                    "nota": detalle.nota
                }
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/recetas/<receta_id>", methods=["PUT"])
@admin_required
def api_recetas_editar(receta_id):
    """
    Edita una receta existente y su detalle.
    Permite cambiar: nombre, quimico_id, dosis, volumen_base
    NO permite cambiar: receta_id (código + número)
    
    Body JSON:
    {
        "nombre": "Tallar Baños Profundo",
        "quimico_id": "QU-DS-001",
        "dosis": 30,
        "volumen_base": 1500
    }
    """
    try:
        receta = Receta.query.get(receta_id)
        
        if not receta:
            return jsonify({"success": False, "error": "Receta no encontrada"}), 404
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nuevo_quimico_id = data.get("quimico_id", "").strip()
        nueva_dosis = data.get("dosis")
        nuevo_volumen = data.get("volumen_base")
        
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        if not nuevo_quimico_id:
            return jsonify({"success": False, "error": "Químico requerido"}), 400
        
        if nueva_dosis is None or nueva_dosis < 0:
            return jsonify({"success": False, "error": "Dosis debe ser 0 o mayor"}), 400
        
        if nuevo_volumen is None or nuevo_volumen < 0:
            return jsonify({"success": False, "error": "Volumen base debe ser 0 o mayor"}), 400
        
        
        # Validar nombre único (excluyendo el actual)
        existe_nombre = Receta.query.filter(
            db.func.upper(Receta.nombre) == nuevo_nombre.upper(),
            Receta.receta_id != receta_id
        ).first()
        
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe otra receta con el nombre '{nuevo_nombre}'"
            }), 400
        
        # Validar que el nuevo químico existe
        quimico = Quimico.query.get(nuevo_quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Químico no encontrado"}), 404
        
        # Actualizar Receta
        receta.nombre = nuevo_nombre
        
        # Actualizar o crear RecetaDetalle (debería existir solo 1)
        detalle = RecetaDetalle.query.filter_by(receta_id=receta_id).first()
        
        if detalle:
            # Actualizar existente
            detalle.quimico_id = nuevo_quimico_id
            detalle.dosis = nueva_dosis
            detalle.volumen_base = nuevo_volumen
            detalle.nota = nuevo_nombre  # ✅ Actualizar nota con nuevo nombre
        else:
            # Crear nuevo (por si no existe)
            detalle = RecetaDetalle(
                receta_id=receta_id,
                quimico_id=nuevo_quimico_id,
                dosis=nueva_dosis,
                unidad_dosis="mL",
                volumen_base=nuevo_volumen,
                unidad_volumen="mL",
                nota=nuevo_nombre
            )
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "receta": {
                "receta_id": receta.receta_id,
                "nombre": receta.nombre,
                "detalle": {
                    "quimico_id": detalle.quimico_id,
                    "dosis": detalle.dosis,
                    "unidad_dosis": detalle.unidad_dosis,
                    "volumen_base": detalle.volumen_base,
                    "unidad_volumen": detalle.unidad_volumen,
                    "nota": detalle.nota
                }
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/recetas/<receta_id>", methods=["DELETE"])
@admin_required
def api_recetas_eliminar(receta_id):
    """
    Elimina una receta y su detalle.
    Valida que NO esté siendo usada en:
    - SopEventoDetalle
    - ElementoDetalle
    - SopFraccionDetalle
    """
    try:
        receta = Receta.query.get(receta_id)
        
        if not receta:
            return jsonify({"success": False, "error": "Receta no encontrada"}), 404
        
        # Validar que no esté en uso
        en_eventos = db.session.query(SopEventoDetalle).filter_by(receta_id=receta_id).count()
        en_elementos = db.session.query(ElementoDetalle).filter_by(receta_id=receta_id).count()
        en_fracciones = db.session.query(SopFraccionDetalle).filter_by(receta_id=receta_id).count()
        
        total_usos = en_eventos + en_elementos + en_fracciones
        
        if total_usos > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta receta está en uso en {total_usos} lugar(es)",
                "detalles": {
                    "eventos": en_eventos,
                    "elementos": en_elementos,
                    "fracciones": en_fracciones
                }
            }), 400
        
        # Eliminar RecetaDetalle primero (por la foreign key)
        RecetaDetalle.query.filter_by(receta_id=receta_id).delete()
        
        # Eliminar Receta
        db.session.delete(receta)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Receta {receta_id} eliminada correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500



@main_bp.route("/api/recetas/fracciones-disponibles", methods=["GET"])
@admin_required
def api_recetas_fracciones_disponibles():
    """
    Retorna fracciones disponibles para crear recetas.
    Incluye nombre_full para distinguir variaciones.
    """
    try:
        # Obtener todas las fracciones ordenadas por código
        fracciones = Fraccion.query.order_by(Fraccion.fraccion_id).all()
        
        fracciones_data = []
        for f in fracciones:
            # Extraer código (ej: FR-MH-001 → MH)
            partes = f.fraccion_id.split('-')
            codigo = partes[1] if len(partes) >= 2 else ''
            
            # Calcular nombre_full
            nombre_full = f.fraccion_nombre
            if f.nombre_custom:
                nombre_full = f"{f.fraccion_nombre} — {f.nombre_custom}"
            
            fracciones_data.append({
                "fraccion_id": f.fraccion_id,
                "codigo": codigo,
                "nombre": f.fraccion_nombre,  # nombre base del glosario
                "nombre_custom": f.nombre_custom,
                "nombre_full": nombre_full  # ← NUEVO
            })
        
        return jsonify({
            "success": True,
            "fracciones": fracciones_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - CONSUMOS (CRUD)
# =========================
@main_bp.route("/api/consumos/next-id", methods=["GET"])
@admin_required
def api_consumos_next_id():
    """
    Genera el próximo ID disponible para consumos.
    Formato fijo: CM-DS-{número}
    Retorna: CM-DS-010
    """
    try:
        # Buscar el último consumo
        pattern = "CM-DS-%"
        ultimo = Consumo.query.filter(
            Consumo.consumo_id.like(pattern)
        ).order_by(
            Consumo.consumo_id.desc()
        ).first()
        
        if ultimo:
            partes = ultimo.consumo_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            siguiente = 1
        
        nuevo_id = f"CM-DS-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "consumo_id": nuevo_id,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/consumos", methods=["POST"])
@admin_required
def api_consumos_crear():
    """
    Crea un nuevo consumo.
    Body JSON:
    {
        "valor": 1,
        "unidad": "disparos",
        "regla": "x m2 = 1 mL"  // opcional
    }
    """
    try:
        data = request.get_json()
        
        valor = data.get("valor")
        unidad = data.get("unidad", "").strip()

        regla = data.get("regla")
        if regla:
            regla = regla.strip() or None
        else:
            regla = None
        
        if valor is None or valor <= 0:
            return jsonify({"success": False, "error": "Valor debe ser mayor a 0"}), 400
        
        if not unidad:
            return jsonify({"success": False, "error": "Unidad requerida"}), 400
        
        if unidad not in ["disparos", "mL"]:
            return jsonify({"success": False, "error": "Unidad debe ser 'disparos' o 'mL'"}), 400
        
        # Generar ID
        pattern = "CM-DS-%"
        ultimo = Consumo.query.filter(
            Consumo.consumo_id.like(pattern)
        ).order_by(
            Consumo.consumo_id.desc()
        ).first()
        
        if ultimo:
            partes = ultimo.consumo_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        consumo_id = f"CM-DS-{siguiente:03d}"
        
        nuevo_consumo = Consumo(
            consumo_id=consumo_id,
            valor=valor,
            unidad=unidad,
            regla=regla
        )
        
        db.session.add(nuevo_consumo)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "consumo": {
                "consumo_id": nuevo_consumo.consumo_id,
                "valor": nuevo_consumo.valor,
                "unidad": nuevo_consumo.unidad,
                "regla": nuevo_consumo.regla
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/consumos/<consumo_id>", methods=["PUT"])
@admin_required
def api_consumos_editar(consumo_id):
    """
    Edita un consumo existente.
    Body JSON:
    {
        "valor": 2,
        "unidad": "disparos",
        "regla": "x m2 = 2 mL"
    }
    """
    try:
        consumo = Consumo.query.get(consumo_id)
        
        if not consumo:
            return jsonify({"success": False, "error": "Consumo no encontrado"}), 404
        
        data = request.get_json()
        
        nuevo_valor = data.get("valor")
        nueva_unidad = data.get("unidad", "").strip()

        nueva_regla = data.get("regla")
        if nueva_regla:
            nueva_regla = nueva_regla.strip() or None
        else:
            nueva_regla = None
        
        if nuevo_valor is None or nuevo_valor <= 0:
            return jsonify({"success": False, "error": "Valor debe ser mayor a 0"}), 400
        
        if not nueva_unidad:
            return jsonify({"success": False, "error": "Unidad requerida"}), 400
        
        if nueva_unidad not in ["disparos", "mL"]:
            return jsonify({"success": False, "error": "Unidad debe ser 'disparos' o 'mL'"}), 400
        
        consumo.valor = nuevo_valor
        consumo.unidad = nueva_unidad
        consumo.regla = nueva_regla
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "consumo": {
                "consumo_id": consumo.consumo_id,
                "valor": consumo.valor,
                "unidad": consumo.unidad,
                "regla": consumo.regla
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/consumos/<consumo_id>", methods=["DELETE"])
@admin_required
def api_consumos_eliminar(consumo_id):
    """
    Elimina un consumo.
    Valida uso en: SopFraccionDetalle, ElementoDetalle, SopEventoDetalle
    """
    try:
        consumo = Consumo.query.get(consumo_id)
        
        if not consumo:
            return jsonify({"success": False, "error": "Consumo no encontrado"}), 404
        
        en_fracciones = db.session.query(SopFraccionDetalle).filter_by(consumo_id=consumo_id).count()
        en_elementos = db.session.query(ElementoDetalle).filter_by(consumo_id=consumo_id).count()
        en_eventos = db.session.query(SopEventoDetalle).filter_by(consumo_id=consumo_id).count()
        
        total_usos = en_fracciones + en_elementos + en_eventos
        
        if total_usos > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Este consumo está en uso en {total_usos} lugar(es)",
                "detalles": {
                    "fracciones": en_fracciones,
                    "elementos": en_elementos,
                    "eventos": en_eventos
                }
            }), 400
        
        db.session.delete(consumo)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Consumo {consumo_id} eliminado correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/catalogos/consumos")
@admin_required
def catalogos_consumos():
    """
    Panel de gestión de Consumos
    """
    # Obtener todos los consumos ordenados por ID
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
    
    return render_template(
        "catalogos/compartidos/consumos.html",
        consumos=consumos
    )


"""
Rutas para Elementos - Catálogos Regulares
Agregar estas rutas a tu archivo principal de rutas (ej: routes.py o main.py)
"""

"""
Rutas para Elementos - Catálogos Regulares
Agregar estas rutas a tu archivo principal de rutas (ej: routes.py o main.py)
"""

# =====================================================
# 🎯 ELEMENTOS - PÁGINA PRINCIPAL
# =====================================================
@main_bp.route('/catalogos/regulares/elementos')
def catalogos_elementos():
    """Página de gestión de elementos"""
    return render_template('catalogos/regulares/elementos.html')


# =====================================================
# 🎯 API: GET /api/elementos/catalogos
# =====================================================
@main_bp.route('/api/elementos/catalogos', methods=['GET'])
def api_elementos_catalogos():
    """
    Obtener datos para poblar dropdowns:
    - Áreas
    - SubÁreas (con su área)
    - Grupos/nombres disponibles (SANITARIO, CESTO, etc.)
    - Descripciones por grupo
    """
    try:
        # 1. Obtener todas las áreas
        areas = Area.query.order_by(Area.orden_area).all()
        areas_data = [
            {
                'area_id': a.area_id,
                'nombre': a.area_nombre
            }
            for a in areas
        ]

        # 2. Obtener todas las subáreas con su área
        subareas = SubArea.query.join(Area).order_by(Area.orden_area, SubArea.orden_subarea).all()
        subareas_data = [
            {
                'subarea_id': sa.subarea_id,
                'nombre': sa.subarea_nombre,
                'area_id': sa.area_id,
                'area_nombre': sa.area.area_nombre
            }
            for sa in subareas
        ]

        # 3. Obtener grupos únicos (nombre) de elementos existentes
        grupos = db.session.query(
            Elemento.nombre
        ).distinct().order_by(Elemento.nombre).all()
        
        grupos_data = [g[0] for g in grupos if g[0]]  # Lista plana de strings

        # 4. Obtener descripciones únicas por grupo
        descripciones_query = db.session.query(
            Elemento.nombre,
            Elemento.descripcion
        ).distinct().order_by(Elemento.nombre, Elemento.descripcion).all()

        # Organizar en diccionario: {nombre: [descripciones]}
        descripciones_por_grupo = {}
        for nombre, descripcion in descripciones_query:
            if nombre not in descripciones_por_grupo:
                descripciones_por_grupo[nombre] = []
            if descripcion:  # Solo agregar si no es NULL
                descripciones_por_grupo[nombre].append(descripcion)

        return jsonify({
            'areas': areas_data,
            'subareas': subareas_data,
            'grupos': grupos_data,
            'descripciones_por_grupo': descripciones_por_grupo
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =====================================================
# 🎯 API: GET /api/elementos
# =====================================================
@main_bp.route('/api/elementos', methods=['GET'])
def api_elementos_list():
    try:
        # Parámetros de paginación
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # Parámetros de filtro
        area_id = request.args.get('area_id')
        subarea_id = request.args.get('subarea_id')

        # Query base
        query = Elemento.query.join(SubArea).join(Area)

        # Aplicar filtros
        if subarea_id:
            query = query.filter(Elemento.subarea_id == subarea_id)
        elif area_id:
            # Si solo hay area_id, filtrar por todas las subareas de esa área
            query = query.filter(SubArea.area_id == area_id)

        # Ordenar por elemento_id
        query = query.order_by(Elemento.elemento_id)

        # Paginar
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Formatear resultados
        elementos_data = [
            {
                'elemento_id': e.elemento_id,
                'nombre': e.nombre,
                'descripcion': e.descripcion,
                'cantidad': e.cantidad,
                'estatus': e.estatus,
                'subarea_id': e.subarea_id,
                'subarea_nombre': e.subarea.subarea_nombre,
                'area_id': e.subarea.area_id,
                'area_nombre': e.subarea.area.area_nombre
            }
            for e in pagination.items
        ]

        return jsonify({
            'elementos': elementos_data,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': pagination.page,
            'per_page': pagination.per_page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =====================================================
# 🎯 API: GET /api/elementos/next-id
# =====================================================
@main_bp.route('/api/elementos/next-id', methods=['GET'])
def api_elementos_next_id():
    
    try:
        CODIGOS_ELEMENTO = {
            'A/C': 'AR',
            'ACCESO': 'AE',
            'ACCESORIO': 'AC',
            'ARCHIVERO': 'AH',
            'BANCO': 'BA',
            'BANQUILLO': 'BN',
            'BASCULA': 'BC',
            'BASE': 'BS',
            'BORDE': ['BO', 'BP'],  # ← Caso especial
            'CAMILLA': 'CA',
            'CESTO': 'CE',
            'CHAPA': 'CH',
            'CUADRO': 'CU',
            'DETECTOR': 'DE',
            'ESCRITORIO': 'EC',
            'ESPEJO': 'ES',
            'EXTINTOR': 'EX',
            'GABINETE': 'GE',
            'LAMPARA': 'LM',
            'LAVABO': 'LA',
            'LIBRERO': 'LI',
            'LUZ': 'LZ',
            'MESA': 'ME',
            'MICROONDAS': 'MI',
            'MUEBLE': 'MU',
            'PARED': 'PR',
            'PERCHERO': 'PE',
            'PROYECCION': 'PO',
            'PROYECTOR': 'PY',
            'PUERTA': 'PU',
            'REFRIGERADOR': 'RE',
            'SANITARIO': 'SA',
            'SEÑALETICA': 'SE',
            'SILLA': 'SI',
            'SOFA': 'SO',
            'TELEVISION': 'TV',
            'TUBERIA': 'TU',
            'VIGA': 'VG',
        }

        nombre = request.args.get('nombre')
        descripcion = request.args.get('descripcion')

        if not nombre or not descripcion:
            return jsonify({'error': 'Faltan parámetros: nombre y descripcion'}), 400

        # Determinar código
        if nombre == 'BORDE':
            # Lógica especial para BORDE
            if 'puerta' in descripcion.lower():
                codigo = 'BP'
            else:
                codigo = 'BO'

        elif nombre in CODIGOS_ELEMENTO:
            codigo = CODIGOS_ELEMENTO[nombre]
        else:
            # Fallback: primeras 2 letras
            codigo = nombre[:2].upper()

        # Buscar el último número usado para este código
        # Patrón: EL-{CODIGO}-%
        patron = f'EL-{codigo}-%'
        
        elementos = Elemento.query.filter(
            Elemento.elemento_id.like(patron)
        ).all()

        # Extraer números de los IDs
        numeros = []
        for elem in elementos:
            try:
                # Formato: EL-SA-001 -> extraer 001
                partes = elem.elemento_id.split('-')
                if len(partes) == 3:
                    num = int(partes[2])
                    numeros.append(num)
            except (ValueError, IndexError):
                continue

        # Calcular siguiente número
        siguiente_num = max(numeros) + 1 if numeros else 1

        # Generar ID
        next_id = f'EL-{codigo}-{siguiente_num:03d}'

        return jsonify({'next_id': next_id}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =====================================================
# 🎯 API: POST /api/elementos
# =====================================================
@main_bp.route('/api/elementos', methods=['POST'])
def api_elementos_create():
    try:
        CODIGOS_ELEMENTO = {
            'A/C': 'AR',
            'ACCESO': 'AE',
            'ACCESORIO': 'AC',
            'ARCHIVERO': 'AH',
            'BANCO': 'BA',
            'BANQUILLO': 'BN',
            'BASCULA': 'BC',
            'BASE': 'BS',
            'BORDE': ['BO', 'BP'],
            'CAMILLA': 'CA',
            'CESTO': 'CE',
            'CHAPA': 'CH',
            'CUADRO': 'CU',
            'DETECTOR': 'DE',
            'ESCRITORIO': 'EC',
            'ESPEJO': 'ES',
            'EXTINTOR': 'EX',
            'GABINETE': 'GE',
            'LAMPARA': 'LM',
            'LAVABO': 'LA',
            'LIBRERO': 'LI',
            'LUZ': 'LZ',
            'MESA': 'ME',
            'MICROONDAS': 'MI',
            'MUEBLE': 'MU',
            'PARED': 'PR',
            'PERCHERO': 'PE',
            'PROYECCION': 'PO',
            'PROYECTOR': 'PY',
            'PUERTA': 'PU',
            'REFRIGERADOR': 'RE',
            'SANITARIO': 'SA',
            'SEÑALETICA': 'SE',
            'SILLA': 'SI',
            'SOFA': 'SO',
            'TELEVISION': 'TV',
            'TUBERIA': 'TU',
            'VIGA': 'VG',
        }

        data = request.get_json()

        # Validaciones
        required_fields = ['subarea_id', 'nombre', 'descripcion', 'cantidad']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo requerido: {field}'}), 400

        # Validar cantidad
        cantidad = data['cantidad']
        if not isinstance(cantidad, (int, float)) or cantidad < 1:
            return jsonify({'error': 'La cantidad debe ser un número mayor o igual a 1'}), 400

        # Validar que subarea_id existe
        subarea = SubArea.query.get(data['subarea_id'])
        if not subarea:
            return jsonify({'error': 'SubÁrea no encontrada'}), 404
      
        nombre = data['nombre'].upper()
        descripcion = data['descripcion']

        # Determinar código
        if nombre == 'BORDE':
            if 'puerta' in descripcion.lower():
                codigo = 'BP'
            else:
                codigo = 'BO'
        elif nombre in CODIGOS_ELEMENTO:
            codigo = CODIGOS_ELEMENTO[nombre]
        else:
            codigo = nombre[:2].upper()
        
        patron = f'EL-{codigo}-%'
        elementos = Elemento.query.filter(Elemento.elemento_id.like(patron)).all()
        
        numeros = []
        for elem in elementos:
            try:
                partes = elem.elemento_id.split('-')
                if len(partes) == 3:
                    num = int(partes[2])
                    numeros.append(num)
            except (ValueError, IndexError):
                continue
        
        siguiente_num = max(numeros) + 1 if numeros else 1
        elemento_id = f'EL-{codigo}-{siguiente_num:03d}'

        # Crear elemento
        nuevo_elemento = Elemento(
            elemento_id=elemento_id,
            subarea_id=data['subarea_id'],
            nombre=nombre,
            descripcion=data['descripcion'],
            cantidad=cantidad,
            estatus='ACTIVO'  # Siempre ACTIVO al crear
        )

        db.session.add(nuevo_elemento)
        db.session.commit()

        return jsonify({
            'message': 'Elemento creado exitosamente',
            'elemento': {
                'elemento_id': nuevo_elemento.elemento_id,
                'nombre': nuevo_elemento.nombre,
                'descripcion': nuevo_elemento.descripcion,
                'cantidad': nuevo_elemento.cantidad,
                'estatus': nuevo_elemento.estatus,
                'subarea_id': nuevo_elemento.subarea_id
            }
        }), 201

    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'error': 'Error de integridad: posiblemente el elemento ya existe'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =====================================================
# 🎯 API: PUT /api/elementos/<elemento_id>
# =====================================================
@main_bp.route('/api/elementos/<elemento_id>', methods=['PUT'])
def api_elementos_update(elemento_id):
    """
    Editar un elemento existente
    Solo permite editar: cantidad, estatus
    
    Body JSON:
    {
        "cantidad": 2,
        "estatus": "INACTIVO"
    }
    """
    try:
        data = request.get_json()

        # Buscar elemento
        elemento = Elemento.query.get(elemento_id)
        if not elemento:
            return jsonify({'error': 'Elemento no encontrado'}), 404

        # Validar campos permitidos
        allowed_fields = ['cantidad', 'estatus']
        for field in data.keys():
            if field not in allowed_fields:
                return jsonify({'error': f'Campo no editable: {field}'}), 400

        # Actualizar cantidad
        if 'cantidad' in data:
            cantidad = data['cantidad']
            if not isinstance(cantidad, (int, float)) or cantidad < 1:
                return jsonify({'error': 'La cantidad debe ser un número mayor o igual a 1'}), 400
            elemento.cantidad = cantidad

        # Actualizar estatus
        if 'estatus' in data:
            estatus = data['estatus'].upper()
            if estatus not in ['ACTIVO', 'INACTIVO']:
                return jsonify({'error': 'Estatus debe ser ACTIVO o INACTIVO'}), 400
            elemento.estatus = estatus

        db.session.commit()

        return jsonify({
            'message': 'Elemento actualizado exitosamente',
            'elemento': {
                'elemento_id': elemento.elemento_id,
                'cantidad': elemento.cantidad,
                'estatus': elemento.estatus
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =====================================================
# 🎯 API: DELETE /api/elementos/<elemento_id>
# =====================================================
@main_bp.route('/api/elementos/<elemento_id>', methods=['DELETE'])
def api_elementos_delete(elemento_id):
    """
    Eliminar un elemento
    Validación: NO debe estar en elemento_detalle
    """
    try:
        # Buscar elemento
        elemento = Elemento.query.get(elemento_id)
        if not elemento:
            return jsonify({'error': 'Elemento no encontrado'}), 404

        # Validar que no esté en uso en elemento_detalle
        en_uso = ElementoDetalle.query.filter_by(elemento_id=elemento_id).first()
        if en_uso:
            return jsonify({
                'error': 'No se puede eliminar el elemento porque está en uso en ElementoDetalle'
            }), 400

        # Eliminar elemento
        db.session.delete(elemento)
        db.session.commit()

        return jsonify({'message': 'Elemento eliminado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =========================
# API - HERRAMIENTAS (CRUD)
# =========================

@main_bp.route("/api/herramientas/catalogos", methods=["GET"])
@admin_required
def api_herramientas_catalogos():
    """
    Obtiene el glosario fijo de grupos de herramientas para el dropdown.
    """
    try:
        GLOSARIO_HERRAMIENTAS = {
            'AT': 'ATOMIZADOR',
            'BA': 'BASTON',
            'BL': 'BOLSA',
            'BS': 'BASE',
            'CA': 'CARRITO',
            'CE': 'CEPILLO',
            'CU': 'CUBETA',
            'EO': 'ESPONJA',
            'EP': 'ESPATULA',
            'ES': 'ESCOBA',
            'EX': 'EXPRIMIDOR',
            'FI': 'FIBRA',
            'GU': 'GUANTES',
            'JA': 'JALADOR',
            'MA': 'MANGUERA',
            'MO': 'MOP',
            'OR': 'ORGANIZADOR',
            'PA': 'PAÑO',
            'PL': 'PLUMERO',
            'RE': 'RECOGEDOR',
            'SE': 'SEÑALETICA',
            'TO': 'TOALLAS',
            'TP': 'TOPE',
            'TR': 'TRAPEADOR',
        }
        
        # Convertir a lista para el frontend
        grupos = [
            {"codigo": codigo, "nombre": nombre}
            for codigo, nombre in sorted(GLOSARIO_HERRAMIENTAS.items())
        ]
        
        return jsonify({
            "success": True,
            "grupos": grupos
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/herramientas/next-id", methods=["GET"])
@admin_required
def api_herramientas_next_id():
    """
    Genera el próximo ID disponible para un grupo específico.
    Query param: grupo (ej: CA, MO, ES)
    Retorna: HE-{grupo}-{número} (ej: HE-CA-002)
    """
    grupo = request.args.get("grupo", "").strip().upper()
    
    if not grupo:
        return jsonify({"success": False, "error": "Grupo requerido"}), 400
    
    if len(grupo) != 2:
        return jsonify({"success": False, "error": "Grupo debe tener 2 caracteres"}), 400
    
    try:
        # Buscar la última herramienta de este grupo
        pattern = f"HE-{grupo}-%"
        ultima = Herramienta.query.filter(
            Herramienta.herramienta_id.like(pattern)
        ).order_by(
            Herramienta.herramienta_id.desc()
        ).first()
        
        if ultima:
            # Extraer el número del ID (ej: "HE-CA-002" → "002" → 2)
            partes = ultima.herramienta_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            # Primera herramienta de este grupo
            siguiente = 1
        
        # Formatear con 3 dígitos (001, 002, ..., 999)
        nuevo_id = f"HE-{grupo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "herramienta_id": nuevo_id,
            "grupo": grupo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/herramientas", methods=["GET"])
@admin_required
def api_herramientas_listar():
    """
    Lista todas las herramientas con paginación y filtros.
    Query params opcionales:
    - page: número de página (default 1)
    - per_page: resultados por página (default 50)
    - grupo: filtrar por grupo (ej: CA, MO)
    - estatus: filtrar por estatus (Activo, Inactivo)
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        grupo = request.args.get('grupo', '').strip().upper()
        estatus = request.args.get('estatus', '').strip()
        
        # Query base
        query = Herramienta.query
        
        # Filtros
        if grupo:
            pattern = f"HE-{grupo}-%"
            query = query.filter(Herramienta.herramienta_id.like(pattern))
        
        if estatus:
            query = query.filter(Herramienta.estatus == estatus)
        
        # Ordenar y paginar
        query = query.order_by(Herramienta.herramienta_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        herramientas_data = [
            {
                'herramienta_id': h.herramienta_id,
                'nombre': h.nombre,
                'descripcion': h.descripcion,
                'estatus': h.estatus,
                'grupo': h.herramienta_id.split('-')[1] if '-' in h.herramienta_id else ''
            }
            for h in pagination.items
        ]
        
        return jsonify({
            "success": True,
            "herramientas": herramientas_data,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/herramientas", methods=["POST"])
@admin_required
def api_herramientas_crear():
    """
    Crea una nueva herramienta.
    Body JSON:
    {
        "grupo": "CA",
        "nombre": "CARRITO",
        "descripcion": "Carrito de limpieza"  // opcional, si vacío usa nombre
    }
    """
    try:
        GLOSARIO_HERRAMIENTAS = {
            'AT': 'ATOMIZADOR', 'BA': 'BASTON', 'BL': 'BOLSA', 'BS': 'BASE',
            'CA': 'CARRITO', 'CE': 'CEPILLO', 'CU': 'CUBETA', 'EO': 'ESPONJA',
            'EP': 'ESPATULA', 'ES': 'ESCOBA', 'EX': 'EXPRIMIDOR', 'FI': 'FIBRA',
            'GU': 'GUANTES', 'JA': 'JALADOR', 'MA': 'MANGUERA', 'MO': 'MOP',
            'OR': 'ORGANIZADOR', 'PA': 'PAÑO', 'PL': 'PLUMERO', 'RE': 'RECOGEDOR',
            'SE': 'SEÑALETICA', 'TO': 'TOALLAS', 'TP': 'TOPE', 'TR': 'TRAPEADOR',
        }
        
        data = request.get_json()
        
        # Validaciones
        grupo = data.get("grupo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        descripcion = data.get("descripcion", "").strip()
        
        # 1. Validar formato de grupo
        if not grupo or len(grupo) != 2:
            return jsonify({"success": False, "error": "Grupo inválido (2 caracteres)"}), 400
        
        # 2. Validar que grupo esté en el glosario
        if grupo not in GLOSARIO_HERRAMIENTAS:
            return jsonify({
                "success": False,
                "error": f"Grupo '{grupo}' no válido. Usa: {', '.join(GLOSARIO_HERRAMIENTAS.keys())}"
            }), 400
        
        # 3. Validar nombre
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # 4. Si descripción vacía, usar nombre
        if not descripcion:
            descripcion = nombre
        
        # 5. Generar ID
        pattern = f"HE-{grupo}-%"
        ultima = Herramienta.query.filter(
            Herramienta.herramienta_id.like(pattern)
        ).order_by(
            Herramienta.herramienta_id.desc()
        ).first()
        
        if ultima:
            partes = ultima.herramienta_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        herramienta_id = f"HE-{grupo}-{siguiente:03d}"
        
        # 6. Crear herramienta
        nueva_herramienta = Herramienta(
            herramienta_id=herramienta_id,
            nombre=nombre,
            descripcion=descripcion,
            estatus='Activo'  # Siempre Activo al crear
        )
        
        db.session.add(nueva_herramienta)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "herramienta": {
                "herramienta_id": nueva_herramienta.herramienta_id,
                "nombre": nueva_herramienta.nombre,
                "descripcion": nueva_herramienta.descripcion,
                "estatus": nueva_herramienta.estatus
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/herramientas/<herramienta_id>", methods=["PUT"])
@admin_required
def api_herramientas_editar(herramienta_id):
    """
    Edita una herramienta existente.
    Solo permite editar: nombre, descripcion, estatus
    NO permite editar: herramienta_id, grupo
    
    Body JSON:
    {
        "nombre": "CARRITO NUEVO",
        "descripcion": "Carrito de limpieza mejorado",
        "estatus": "Activo"  // Activo o Inactivo
    }
    """
    try:
        herramienta = Herramienta.query.get(herramienta_id)
        
        if not herramienta:
            return jsonify({"success": False, "error": "Herramienta no encontrada"}), 404
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_descripcion = data.get("descripcion", "").strip()
        nuevo_estatus = data.get("estatus", "").strip()
        
        # Validaciones
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        if not nueva_descripcion:
            return jsonify({"success": False, "error": "Descripción requerida"}), 400
        
        if nuevo_estatus not in ['Activo', 'Inactivo']:
            return jsonify({"success": False, "error": "Estatus debe ser 'Activo' o 'Inactivo'"}), 400
        
        # Actualizar
        herramienta.nombre = nuevo_nombre
        herramienta.descripcion = nueva_descripcion
        herramienta.estatus = nuevo_estatus
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "herramienta": {
                "herramienta_id": herramienta.herramienta_id,
                "nombre": herramienta.nombre,
                "descripcion": herramienta.descripcion,
                "estatus": herramienta.estatus
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/herramientas/<herramienta_id>", methods=["DELETE"])
@admin_required
def api_herramientas_eliminar(herramienta_id):
    """
    Elimina una herramienta.
    Valida que NO esté siendo usada en kit_detalle.
    """
    try:
        herramienta = Herramienta.query.get(herramienta_id)
        
        if not herramienta:
            return jsonify({"success": False, "error": "Herramienta no encontrada"}), 404
        
        # Validar que no esté en kits
        en_kits = KitDetalle.query.filter_by(herramienta_id=herramienta_id).count()
        
        if en_kits > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta herramienta está en {en_kits} kit(s)"
            }), 400
        
        # Eliminar
        db.session.delete(herramienta)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Herramienta {herramienta_id} eliminada correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    
@main_bp.route("/catalogos/herramientas")
@admin_required
def catalogos_herramientas():
    return render_template("catalogos/regulares/herramientas.html")


# =========================
# API - KITS (CRUD)
# =========================
@main_bp.route("/api/kits/fracciones-disponibles", methods=["GET"])
@admin_required
def api_kits_fracciones_disponibles():
    """
    Retorna fracciones disponibles para crear kits.
    Incluye nombre_full para distinguir variaciones.
    """
    try:
        # Obtener todas las fracciones ordenadas por código
        fracciones = Fraccion.query.order_by(Fraccion.fraccion_id).all()
        
        fracciones_data = []
        for f in fracciones:
            # Extraer código (ej: FR-MH-001 → MH)
            partes = f.fraccion_id.split('-')
            codigo = partes[1] if len(partes) >= 2 else ''
            
            # Calcular nombre_full
            nombre_full = f.fraccion_nombre
            if f.nombre_custom:
                nombre_full = f"{f.fraccion_nombre} — {f.nombre_custom}"
            
            fracciones_data.append({
                "fraccion_id": f.fraccion_id,
                "codigo": codigo,
                "nombre": f.fraccion_nombre,  # nombre base del glosario
                "nombre_custom": f.nombre_custom,
                "nombre_full": nombre_full  # ← NUEVO
            })
        
        return jsonify({
            "success": True,
            "fracciones": fracciones_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits/herramientas-disponibles", methods=["GET"])
@admin_required
def api_kits_herramientas_disponibles():
    """
    Lista todas las herramientas activas para checkboxes.
    Query params opcionales:
    - grupo: filtrar por grupo (ej: CA, MO)
    """
    try:
        grupo = request.args.get('grupo', '').strip().upper()
        
        # Query base - solo herramientas activas
        query = Herramienta.query.filter_by(estatus='Activo')
        
        # Filtro por grupo
        if grupo:
            pattern = f"HE-{grupo}-%"
            query = query.filter(Herramienta.herramienta_id.like(pattern))
        
        herramientas = query.order_by(Herramienta.herramienta_id.asc()).all()
        
        return jsonify({
            "success": True,
            "herramientas": [
                {
                    "herramienta_id": h.herramienta_id,
                    "nombre": h.nombre,
                    "descripcion": h.descripcion,
                    "grupo": h.herramienta_id.split('-')[1] if '-' in h.herramienta_id else ''
                }
                for h in herramientas
            ]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits/next-id", methods=["GET"])
@admin_required
def api_kits_next_id():
    """
    Genera el próximo ID disponible para un código de fracción.
    Query param: codigo (ej: TL, SA)
    Retorna: KT-{codigo}-{número} (ej: KT-TL-002)
    """
    codigo = request.args.get("codigo", "").strip().upper()
    
    if not codigo:
        return jsonify({"success": False, "error": "Código requerido"}), 400
    
    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
    
    try:
        # Buscar el último kit de este código
        pattern = f"KT-{codigo}-%"
        ultimo = Kit.query.filter(
            Kit.kit_id.like(pattern)
        ).order_by(
            Kit.kit_id.desc()
        ).first()
        
        if ultimo:
            partes = ultimo.kit_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            siguiente = 1
        
        nuevo_id = f"KT-{codigo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "kit_id": nuevo_id,
            "codigo": codigo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits", methods=["GET"])
@admin_required
def api_kits_listar():
    """
    Lista todos los kits con sus herramientas.
    Query params opcionales:
    - page: número de página (default 1)
    - per_page: resultados por página (default 50)
    - fraccion: filtrar por código de fracción (ej: TL)
    - nivel: filtrar por nivel (1, 2, 3, 4, o 'general' para NULL)
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        fraccion = request.args.get('fraccion', '').strip().upper()
        nivel = request.args.get('nivel', '').strip()
        tipo_kit = request.args.get('tipo_kit', '').strip()
        
        # Query base
        query = Kit.query
        
        # Filtros
        if fraccion:
            pattern = f"KT-{fraccion}-%"
            query = query.filter(Kit.kit_id.like(pattern))
        
        if nivel:
            if nivel == 'general':
                query = query.filter(Kit.nivel_limpieza_id.is_(None))
            else:
                query = query.filter(Kit.nivel_limpieza_id == int(nivel))

        if tipo_kit:
            query = query.filter_by(tipo_kit=tipo_kit)
        
        # Ordenar y paginar
        query = query.order_by(Kit.kit_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Formatear con herramientas
        kits_data = []
        for k in pagination.items:
            # Obtener herramientas del kit
            detalles = KitDetalle.query.filter_by(kit_id=k.kit_id).all()
            herramientas = [
                {
                    'herramienta_id': d.herramienta_id,
                    'nombre': d.herramienta.nombre if d.herramienta else '',
                    'nota': d.nota
                }
                for d in detalles
            ]
            
            kits_data.append({
                'kit_id': k.kit_id,
                'fraccion_id': k.fraccion_id,
                'nivel_limpieza_id': k.nivel_limpieza_id,
                'nombre': k.nombre,
                'tipo_kit': k.tipo_kit,
                'codigo': k.kit_id.split('-')[1] if '-' in k.kit_id else '',
                'herramientas': herramientas,
                'cantidad_herramientas': len(herramientas)
            })
        
        return jsonify({
            "success": True,
            "kits": kits_data,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits", methods=["POST"])
@admin_required
def api_kits_crear():
    """
    Crea un nuevo kit con sus herramientas.
    Body JSON:
    {
        "codigo": "MH",
        "fraccion_id": "FR-MH-002",
        "nombre": "Kit Mop Húmedo",
        "nivel_limpieza_id": null,  // null = general, o 1, 2, 3, 4
        "herramientas": ["HE-CE-001", "HE-FI-001"]
    }
    """
    try:
        data = request.get_json()
        
        codigo = data.get("codigo", "").strip().upper()
        fraccion_id = data.get("fraccion_id", "").strip()
        nombre = data.get("nombre", "").strip()
        nivel_limpieza_id = data.get("nivel_limpieza_id")
        herramientas_ids = data.get("herramientas", [])

        # 1. Validar código y fraccion_id
        if not codigo or not fraccion_id:
            return jsonify({"success": False, "error": "Código y fracción requeridos"}), 400
        
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
        
        # 2. Validar que fraccion_id existe
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": f"Fracción {fraccion_id} no encontrada"}), 404
        
        # 3. Validar nombre
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # 4. Validar nivel de limpieza
        if nivel_limpieza_id is not None:
            if nivel_limpieza_id not in [1, 2, 3, 4]:
                return jsonify({"success": False, "error": "Nivel debe ser 1, 2, 3, 4 o null"}), 400
        
        # 5. Validar que tenga al menos 1 herramienta
        if not herramientas_ids or len(herramientas_ids) == 0:
            return jsonify({"success": False, "error": "Debe seleccionar al menos 1 herramienta"}), 400
        
        # 6. Validar que todas las herramientas existan
        for h_id in herramientas_ids:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        
        # 7. Generar ID del kit
        pattern = f"KT-{codigo}-%"
        ultimo = Kit.query.filter(
            Kit.kit_id.like(pattern)
        ).order_by(
            Kit.kit_id.desc()
        ).first()
        
        if ultimo:
            partes = ultimo.kit_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        kit_id = f"KT-{codigo}-{siguiente:03d}"
        
        # 8. Crear Kit (usar fraccion_id del frontend)
        nuevo_kit = Kit(
            kit_id=kit_id,
            fraccion_id=fraccion_id,  # ✅ Usar el fraccion_id específico
            nivel_limpieza_id=nivel_limpieza_id,
            nombre=nombre,
            tipo_kit='sop',
            caso_id=None
        )
        
        db.session.add(nuevo_kit)
        db.session.flush()
        
        # 9. Crear KitDetalle para cada herramienta
        for h_id in herramientas_ids:
            detalle = KitDetalle(
                kit_id=kit_id,
                herramienta_id=h_id,
                nota=nombre
            )
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "kit": {
                "kit_id": nuevo_kit.kit_id,
                "fraccion_id": nuevo_kit.fraccion_id,
                "nivel_limpieza_id": nuevo_kit.nivel_limpieza_id,
                "nombre": nuevo_kit.nombre,
                "herramientas": herramientas_ids
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits/<kit_id>", methods=["PUT"])
@admin_required
def api_kits_editar(kit_id):
    """
    Edita un kit existente.
    Solo permite editar: nombre, nivel_limpieza_id, herramientas
    NO permite editar: kit_id, fraccion_id
    
    Body JSON:
    {
        "nombre": "Kit Tallar Baño Profundo",
        "nivel_limpieza_id": 4,
        "herramientas": ["HE-CE-001", "HE-FI-002"]  // Nueva lista de herramientas
    }
    """
    try:
        kit = Kit.query.get(kit_id)
        
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nuevo_nivel = data.get("nivel_limpieza_id")
        nuevas_herramientas = data.get("herramientas", [])
        
        # Validaciones
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        if nuevo_nivel is not None:
            if nuevo_nivel not in [1, 2, 3, 4]:
                return jsonify({"success": False, "error": "Nivel debe ser 1, 2, 3, 4 o null"}), 400
        
        if not nuevas_herramientas or len(nuevas_herramientas) == 0:
            return jsonify({"success": False, "error": "Debe tener al menos 1 herramienta"}), 400
        
        # Validar herramientas
        for h_id in nuevas_herramientas:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        
        # Actualizar Kit
        kit.nombre = nuevo_nombre
        kit.nivel_limpieza_id = nuevo_nivel
        
        # Actualizar herramientas - eliminar todas y recrear
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        
        for h_id in nuevas_herramientas:
            detalle = KitDetalle(
                kit_id=kit_id,
                herramienta_id=h_id,
                nota=nuevo_nombre  # Actualizar nota con nuevo nombre
            )
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "kit": {
                "kit_id": kit.kit_id,
                "fraccion_id": kit.fraccion_id,
                "nivel_limpieza_id": kit.nivel_limpieza_id,
                "nombre": kit.nombre,
                "herramientas": nuevas_herramientas
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits/<kit_id>", methods=["DELETE"])
@admin_required
def api_kits_eliminar(kit_id):
    """
    Elimina un kit y sus herramientas.
    Valida que NO esté siendo usado en:
    - SopFraccionDetalle
    - ElementoDetalle
    - (Agregar otras tablas según necesites)
    """
    try:
        kit = Kit.query.get(kit_id)
        
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        
        # Validar que no esté en uso (agregar validaciones según tus tablas)
        # Ejemplo:
        # en_sop = SopFraccionDetalle.query.filter_by(kit_id=kit_id).count()
        # if en_sop > 0:
        #     return jsonify({
        #         "success": False,
        #         "error": f"No se puede eliminar. Este kit está en {en_sop} SOP(s)"
        #     }), 400
        
        # Eliminar KitDetalle primero
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        
        # Eliminar Kit
        db.session.delete(kit)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Kit {kit_id} eliminado correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/catalogos/kits")
@admin_required
def catalogos_kits():
    return render_template("catalogos/regulares/kits.html")



# =========================
# CATÁLOGOS - FRACCIONES
# =========================

@main_bp.route("/catalogos/fracciones")
@admin_required
def catalogos_fracciones():
    """Panel de gestión de Fracciones"""
    return render_template("catalogos/regulares/fracciones.html")


# =========================
# API - FRACCIONES (CRUD)
# =========================

@main_bp.route("/api/fracciones/catalogos", methods=["GET"])
@admin_required
def api_fracciones_catalogos():
    """
    Obtiene el glosario de fracciones para dropdown.
    Retorna códigos con sus nombres base.
    """
    try:
        GLOSARIO_FRACCIONES = {
            'SE': 'Colocar Señalética',
            'BS': 'Sacar Basura',
            'SP': 'Sacudir Superficies',
            'VI': 'Limpiar Vidrios',
            'BA': 'Barrer',
            'TL': 'Tallar Baño',
            'CN': 'Reabastecer Consumibles',
            'SA': 'Sacudir Elementos',
            'TA': 'Lavar Trastes',
            'AC': 'Acomodar Trastes',
            'MS': 'Mop Seco',
            'MH': 'Mop Húmedo',
            'TR': 'Trapear',
        }
        
        # Convertir a lista para el frontend
        grupos = [
            {"codigo": codigo, "nombre": nombre}
            for codigo, nombre in sorted(GLOSARIO_FRACCIONES.items())
        ]
        
        # Obtener grupos de fracciones únicos (administracion/produccion)
        grupos_fracciones = db.session.query(
            Fraccion.grupo_fracciones
        ).filter(
            Fraccion.grupo_fracciones.isnot(None),
            Fraccion.grupo_fracciones != ''
        ).distinct().all()
        
        grupos_frac = sorted([g[0] for g in grupos_fracciones if g[0]])
        
        return jsonify({
            "success": True,
            "grupos": grupos,
            "grupos_fracciones": grupos_frac if grupos_frac else ["administracion", "produccion"]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones/next-id", methods=["GET"])
@admin_required
def api_fracciones_next_id():
    """
    Genera el próximo ID disponible para un código específico.
    Query param: codigo (ej: BS, TL, SP)
    Retorna: 
    - fraccion_id: FR-{codigo}-{número}
    - es_primera: true si es 001, false si es 002+
    - customs_existentes: lista de customs ya usados en este código
    """
    codigo = request.args.get("codigo", "").strip().upper()
    
    if not codigo:
        return jsonify({"success": False, "error": "Código requerido"}), 400
    
    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
    
    try:
        # Buscar la última fracción de este código
        pattern = f"FR-{codigo}-%"
        ultima = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern)
        ).order_by(
            Fraccion.fraccion_id.desc()
        ).first()
        
        if ultima:
            # Extraer el número del ID (ej: "FR-BS-004" → "004" → 4)
            partes = ultima.fraccion_id.split('-')
            if len(partes) == 3:
                try:
                    numero_actual = int(partes[2])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            # Primera fracción de este código
            siguiente = 1
        
        # Formatear con 3 dígitos (001, 002, ..., 999)
        nuevo_id = f"FR-{codigo}-{siguiente:03d}"
        
        # ✅ NUEVO: Determinar si es primera
        es_primera = (siguiente == 1)
        
        # ✅ NUEVO: Obtener customs existentes de este código
        customs_existentes = []
        if not es_primera:
            fracciones_codigo = Fraccion.query.filter(
                Fraccion.fraccion_id.like(pattern)
            ).all()
            
            for f in fracciones_codigo:
                if f.nombre_custom:
                    customs_existentes.append(f.nombre_custom)
        
        return jsonify({
            "success": True,
            "fraccion_id": nuevo_id,
            "codigo": codigo,
            "numero": siguiente,
            "es_primera": es_primera,  # ✅ NUEVO
            "customs_existentes": customs_existentes  # ✅ NUEVO
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/api/fracciones", methods=["GET"])
@admin_required
def api_fracciones_listar():
    """
    Lista todas las fracciones con paginación y filtros.
    Query params opcionales:
    - page: número de página (default 1)
    - per_page: resultados por página (default 50)
    - grupo: filtrar por grupo_fracciones (administracion/produccion)
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        grupo = request.args.get('grupo', '').strip()
        
        # Query base
        query = Fraccion.query
        
        # Filtro por grupo_fracciones
        if grupo:
            query = query.filter(Fraccion.grupo_fracciones == grupo)
        
        # Ordenar y paginar
        query = query.order_by(Fraccion.fraccion_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Formatear resultados
        fracciones_data = []
        for f in pagination.items:
            # ✅ NUEVO: Obtener niveles configurados
            niveles = db.session.query(Metodologia.nivel_limpieza_id)\
                .filter_by(fraccion_id=f.fraccion_id)\
                .order_by(Metodologia.nivel_limpieza_id)\
                .all()
            
            niveles_ids = [n[0] for n in niveles]  # [1, 2, 3]
            
            # Mapeo a letras
            nivel_map = {1: 'B', 2: 'M', 3: 'P', 4: 'E'}
            niveles_letras = [nivel_map.get(n, str(n)) for n in niveles_ids]
            
            fracciones_data.append({
                'fraccion_id': f.fraccion_id,
                'fraccion_nombre': f.fraccion_nombre,  # nombre base
                'nombre_custom': f.nombre_custom,
                'nota_tecnica': f.nota_tecnica,
                'grupo_fracciones': f.grupo_fracciones,
                'codigo': f.fraccion_id.split('-')[1] if '-' in f.fraccion_id else '',
                'niveles': niveles_ids,  # ✅ [1, 2, 3]
                'niveles_display': ' '.join(niveles_letras)  # ✅ "B M P"
            })
        
        return jsonify({
            "success": True,
            "fracciones": fracciones_data,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones", methods=["POST"])
@admin_required
def api_fracciones_crear():
    """
    Crea una nueva fracción.
    Body JSON:
    {
        "codigo": "BS",
        "nombre_custom": "Producción",  // Obligatorio si es 002+, prohibido si es 001
        "nota_tecnica": "...",
        "grupo_fracciones": "administracion"
    }
    """
    try:
        GLOSARIO_FRACCIONES = {
            'SE': 'Colocar Señalética',
            'BS': 'Sacar Basura',
            'SP': 'Sacudir Superficies',
            'VI': 'Limpiar Vidrios',
            'BA': 'Barrer',
            'TL': 'Tallar Baño',
            'CN': 'Reabastecer Consumibles',
            'SA': 'Sacudir Elementos',
            'TA': 'Lavar Trastes',
            'AC': 'Acomodar Trastes',
            'MS': 'Mop Seco',
            'MH': 'Mop Húmedo',
            'TR': 'Trapear',
        }
        
        data = request.get_json()
        
        # Validaciones básicas
        codigo = data.get("codigo", "").strip().upper()
        nombre_custom = data.get("nombre_custom", "").strip() or None
        nota_tecnica = data.get("nota_tecnica", "").strip() or None
        grupo_fracciones = data.get("grupo_fracciones", "").strip() or None
        
        # 1. Validar código
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Código inválido (2 caracteres)"}), 400
        
        # 2. Validar que código esté en glosario
        if codigo not in GLOSARIO_FRACCIONES:
            return jsonify({
                "success": False,
                "error": f"Código '{codigo}' no válido. Usa: {', '.join(GLOSARIO_FRACCIONES.keys())}"
            }), 400
        
        # 3. Obtener nombre base del glosario
        nombre_base = GLOSARIO_FRACCIONES[codigo]
        
        # 4. Validar grupo_fracciones
        if grupo_fracciones and grupo_fracciones not in ['administracion', 'produccion']:
            return jsonify({"success": False, "error": "Grupo debe ser 'administracion' o 'produccion'"}), 400
        
        # 5. Generar ID y determinar si es primera
        pattern = f"FR-{codigo}-%"
        ultima = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern)
        ).order_by(
            Fraccion.fraccion_id.desc()
        ).first()
        
        if ultima:
            partes = ultima.fraccion_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        fraccion_id = f"FR-{codigo}-{siguiente:03d}"
        es_primera = (siguiente == 1)
        
        # ✅ 6. VALIDACIONES DE NOMBRE_CUSTOM según es_primera
        if es_primera:
            # FR-XX-001: Custom NO permitido
            if nombre_custom:
                return jsonify({
                    "success": False,
                    "error": "La primera fracción no debe tener nombre custom (usa el nombre base del glosario)"
                }), 400
        else:
            # FR-XX-002+: Custom OBLIGATORIO
            if not nombre_custom:
                return jsonify({
                    "success": False,
                    "error": f"Este código ya existe ({fraccion_id}). Debes agregar un nombre custom para diferenciarlo"
                }), 400
            
            # Validar que custom no sea igual al nombre base
            if nombre_custom.upper() == nombre_base.upper():
                return jsonify({
                    "success": False,
                    "error": "El nombre custom no puede ser igual al nombre base"
                }), 400
            
            # Validar que custom no esté repetido en este código
            custom_duplicado = Fraccion.query.filter(
                Fraccion.fraccion_id.like(pattern),
                db.func.upper(Fraccion.nombre_custom) == nombre_custom.upper()
            ).first()
            
            if custom_duplicado:
                return jsonify({
                    "success": False,
                    "error": f"Ya existe otra fracción de este código con el custom '{nombre_custom}'"
                }), 400
        
        # 7. Crear fracción
        nueva_fraccion = Fraccion(
            fraccion_id=fraccion_id,
            fraccion_nombre=nombre_base,
            nombre_custom=nombre_custom,
            nota_tecnica=nota_tecnica,
            grupo_fracciones=grupo_fracciones
        )
        
        db.session.add(nueva_fraccion)
        db.session.commit()
        
        # Calcular nombre_full para respuesta
        nombre_full = nombre_base
        if nombre_custom:
            nombre_full = f"{nombre_base} — {nombre_custom}"
        
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_id": nueva_fraccion.fraccion_id,
                "fraccion_nombre": nueva_fraccion.fraccion_nombre,
                "nombre_custom": nueva_fraccion.nombre_custom,
                "nombre_full": nombre_full,
                "nota_tecnica": nueva_fraccion.nota_tecnica,
                "grupo_fracciones": nueva_fraccion.grupo_fracciones,
                "es_primera": es_primera  # ✅ Para el mensaje de éxito
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/api/fracciones/<fraccion_id>", methods=["PUT"])
@admin_required
def api_fracciones_editar(fraccion_id):
    """
    Edita una fracción existente.
    Solo permite editar: nombre_custom, nota_tecnica, grupo_fracciones
    NO permite editar: fraccion_id, fraccion_nombre (viene del glosario)
    
    Body JSON:
    {
        "nombre_custom": "Nueva Variación",
        "nota_tecnica": "...",
        "grupo_fracciones": "produccion"
    }
    """
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        data = request.get_json()
        
        nuevo_custom = data.get("nombre_custom", "").strip() or None
        nueva_nota = data.get("nota_tecnica", "").strip() or None
        nuevo_grupo = data.get("grupo_fracciones", "").strip() or None
        
        # Validar grupo_fracciones
        if nuevo_grupo and nuevo_grupo not in ['administracion', 'produccion']:
            return jsonify({"success": False, "error": "Grupo debe ser 'administracion' o 'produccion'"}), 400
        
        # Actualizar
        fraccion.nombre_custom = nuevo_custom
        fraccion.nota_tecnica = nueva_nota
        fraccion.grupo_fracciones = nuevo_grupo
        
        db.session.commit()
        
        # Calcular nombre_full para respuesta
        nombre_full = fraccion.fraccion_nombre
        if nuevo_custom:
            nombre_full = f"{fraccion.fraccion_nombre} — {nuevo_custom}"
        
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_id": fraccion.fraccion_id,
                "fraccion_nombre": fraccion.fraccion_nombre,
                "nombre_custom": fraccion.nombre_custom,
                "nombre_full": nombre_full,
                "nota_tecnica": fraccion.nota_tecnica,
                "grupo_fracciones": fraccion.grupo_fracciones
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones/<fraccion_id>", methods=["DELETE"])
@admin_required
def api_fracciones_eliminar(fraccion_id):
    """
    Elimina una fracción.
    
    Validaciones:
    - No debe estar en uso en SOPs
    - No debe estar en elemento_sets
    - No debe estar en kits
    - Si tiene metodologías SIN usar → se borran en cascada
    """
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        # ===== VALIDAR USO EN SISTEMA =====
        
        # 1. ¿Está en SOPs?
        sops_count = db.session.query(SopFraccion).filter_by(fraccion_id=fraccion_id).count()
        
        # 2. ¿Está en elemento_sets?
        elemento_sets_count = db.session.query(ElementoSet).filter_by(fraccion_id=fraccion_id).count()
        
        # 3. ¿Está en kits?
        from app.models import Kit  # Asegúrate de importar si no está
        kits_count = db.session.query(Kit).filter(
            Kit.fraccion_id == fraccion_id
        ).count()
        
        # Si está en uso → NO BORRAR
        if sops_count > 0 or elemento_sets_count > 0 or kits_count > 0:
            return jsonify({
                "success": False,
                "error": "No se puede eliminar. La fracción está en uso.",
                "detalles": {
                    "sops": sops_count,
                    "elemento_sets": elemento_sets_count,
                    "kits": kits_count,
                    "metodologias": 0  # No importa, no se puede borrar por otras razones
                }
            }), 400
        
        # ===== SI NO ESTÁ EN USO: BORRAR EN CASCADA =====
        
        # Obtener todas las metodologías de esta fracción
        metodologias = Metodologia.query.filter_by(fraccion_id=fraccion_id).all()
        
        metodologias_borradas = []
        
        for met in metodologias:
            metodologia_base_id = met.metodologia_base_id
            
            # Verificar si esta metodologia_base está siendo usada por otras fracciones
            otras_fracciones = Metodologia.query.filter(
                Metodologia.metodologia_base_id == metodologia_base_id,
                Metodologia.fraccion_id != fraccion_id
            ).count()
            
            if otras_fracciones > 0:
                # Esta metodologia_base está siendo usada por otras fracciones
                # Solo borramos el link, NO la metodologia_base
                db.session.delete(met)
            else:
                # Esta metodologia_base SOLO la usa esta fracción
                # Borrar todo: link + pasos + metodologia_base
                
                # 1. Borrar pasos
                MetodologiaBasePaso.query.filter_by(
                    metodologia_base_id=metodologia_base_id
                ).delete()
                
                # 2. Borrar link
                db.session.delete(met)
                
                # 3. Borrar metodologia_base
                metodologia_base = MetodologiaBase.query.get(metodologia_base_id)
                if metodologia_base:
                    db.session.delete(metodologia_base)
                    metodologias_borradas.append(metodologia_base_id)
        
        # Borrar la fracción
        db.session.delete(fraccion)
        
        db.session.commit()
        
        mensaje = f"Fracción {fraccion_id} eliminada correctamente"
        if metodologias_borradas:
            mensaje += f"\n\nMetodologías eliminadas: {', '.join(metodologias_borradas)}"
        
        return jsonify({
            "success": True,
            "message": mensaje,
            "metodologias_borradas": metodologias_borradas
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/catalogos/fracciones/<fraccion_id>/metodologias")
@admin_required
def fraccion_metodologias(fraccion_id):
    """Página de configuración de metodologías de una fracción"""
    
    # Validar que la fracción existe
    fraccion = Fraccion.query.get(fraccion_id)
    
    if not fraccion:
        flash(f"Fracción {fraccion_id} no encontrada", "error")
        return redirect(url_for('main.catalogos_fracciones'))
    
    return render_template(
        "catalogos/regulares/metodologias_fraccion.html",
        fraccion=fraccion
    )

@main_bp.route("/api/fracciones/<fraccion_id>/metodologias", methods=["GET"])
@admin_required
def api_fraccion_metodologias_get(fraccion_id):
    """
    Obtiene las metodologías configuradas para los 4 niveles de una fracción.
    
    Returns:
    {
        "success": true,
        "fraccion": {...},
        "metodologias": {
            "1": {"metodologia_base_id": "MB-XX-001-B", "pasos": [...]},
            "2": {"metodologia_base_id": "MB-XX-001-M", "pasos": [...]},
            "3": null,
            "4": null
        }
    }
    """
    try:
        # Validar fracción
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        # Obtener metodologías de los 4 niveles
        metodologias_data = {}
        
        for nivel_id in [1, 2, 3, 4]:
            # Buscar asignación en tabla metodologia
            metodologia_asignacion = Metodologia.query.filter_by(
                fraccion_id=fraccion_id,
                nivel_limpieza_id=nivel_id
            ).first()
            
            if metodologia_asignacion:
                # Obtener metodología base y pasos
                mb = metodologia_asignacion.metodologia_base
                
                pasos = []
                for paso in mb.pasos:
                    pasos.append({
                        "orden": paso.orden,
                        "instruccion": paso.instruccion
                    })
                
                metodologias_data[str(nivel_id)] = {
                    "metodologia_base_id": mb.metodologia_base_id,
                    "nombre": mb.nombre,
                    "descripcion": mb.descripcion,
                    "pasos": pasos
                }
            else:
                # No existe metodología para este nivel
                metodologias_data[str(nivel_id)] = None
        
        # Calcular nombre_full
        nombre_full = fraccion.fraccion_nombre
        if fraccion.nombre_custom:
            nombre_full = f"{fraccion.fraccion_nombre} — {fraccion.nombre_custom}"
        
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_id": fraccion.fraccion_id,
                "fraccion_nombre": fraccion.fraccion_nombre,
                "nombre_custom": fraccion.nombre_custom,
                "nombre_full": nombre_full,
                "codigo": fraccion.fraccion_id.split('-')[1] if '-' in fraccion.fraccion_id else ''
            },
            "metodologias": metodologias_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    

@main_bp.route("/api/fracciones/<fraccion_id>/metodologias/<int:nivel_id>", methods=["POST"])
@admin_required
def api_fraccion_metodologias_save(fraccion_id, nivel_id):
    """
    Guarda/actualiza la metodología de un nivel específico.
    
    Body JSON:
    {
        "pasos": [
            {"orden": 1, "instruccion": "Paso 1"},
            {"orden": 2, "instruccion": "Paso 2"}
        ]
    }
    
    Proceso:
    1. Genera/obtiene ID de metodologia_base: MB-{CODIGO}-{NUM}-{NIVEL}
    2. Crea/actualiza metodologia_base
    3. Borra pasos viejos
    4. Inserta pasos nuevos
    5. Crea/actualiza link en tabla metodologia
    """
    try:
        # Validar fracción
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        # Validar nivel
        if nivel_id not in [1, 2, 3, 4]:
            return jsonify({"success": False, "error": "Nivel inválido (1-4)"}), 400
        
        # Validar nivel_limpieza existe
        nivel_limpieza = NivelLimpieza.query.get(nivel_id)
        if not nivel_limpieza:
            return jsonify({"success": False, "error": f"Nivel de limpieza {nivel_id} no encontrado"}), 404
        
        # Obtener pasos del body
        data = request.get_json()
        pasos = data.get("pasos", [])
        
        # Validar que haya al menos 1 paso
        if len(pasos) == 0:
            return jsonify({"success": False, "error": "Debe haber al menos 1 paso"}), 400
        
        # Validar que todos los pasos tengan instrucción
        for paso in pasos:
            if not paso.get("instruccion", "").strip():
                return jsonify({"success": False, "error": "Todos los pasos deben tener instrucción"}), 400
        
        # Generar ID de metodologia_base
        nivel_letra_map = {1: 'B', 2: 'M', 3: 'P', 4: 'E'}
        nivel_letra = nivel_letra_map[nivel_id]
        
        # Extraer código y número de fraccion_id
        # Ejemplo: FR-BS-001 → codigo=BS, numero=001
        partes = fraccion_id.split('-')
        if len(partes) != 3:
            return jsonify({"success": False, "error": "Formato de fraccion_id inválido"}), 400
        
        codigo = partes[1]
        numero = partes[2]
        
        metodologia_base_id = f"MB-{codigo}-{numero}-{nivel_letra}"
        
        # Buscar si ya existe metodologia_base
        metodologia_base = MetodologiaBase.query.get(metodologia_base_id)
        
        if not metodologia_base:
            # Crear nueva metodologia_base
            nombre_base = fraccion.fraccion_nombre
            
            metodologia_base = MetodologiaBase(
                metodologia_base_id=metodologia_base_id,
                nombre=f"{nombre_base}-{nivel_letra}",
                descripcion=fraccion.fraccion_nombre
            )
            db.session.add(metodologia_base)
            db.session.flush()  # Para que esté disponible para los pasos
        
        # Borrar pasos viejos
        MetodologiaBasePaso.query.filter_by(
            metodologia_base_id=metodologia_base_id
        ).delete()
        
        # Insertar pasos nuevos
        for paso in pasos:
            nuevo_paso = MetodologiaBasePaso(
                metodologia_base_id=metodologia_base_id,
                orden=paso["orden"],
                instruccion=paso["instruccion"].strip()
            )
            db.session.add(nuevo_paso)
        
        # Crear/actualizar link en tabla metodologia
        metodologia_link = Metodologia.query.filter_by(
            fraccion_id=fraccion_id,
            nivel_limpieza_id=nivel_id
        ).first()
        
        if not metodologia_link:
            # Crear nuevo link
            metodologia_link = Metodologia(
                fraccion_id=fraccion_id,
                nivel_limpieza_id=nivel_id,
                metodologia_base_id=metodologia_base_id
            )
            db.session.add(metodologia_link)
        else:
            # Actualizar link existente (por si cambió la metodologia_base)
            metodologia_link.metodologia_base_id = metodologia_base_id
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "metodologia_base_id": metodologia_base_id,
            "total_pasos": len(pasos),
            "message": f"Metodología {metodologia_base_id} guardada correctamente"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - KITS EVENTOS (CRUD)
# =========================
@main_bp.route("/catalogos/kits-eventos")
@admin_required
def catalogos_kits_eventos():
    return render_template("catalogos/eventos/kits_eventos.html")


@main_bp.route("/api/kits-eventos/eventos-disponibles", methods=["GET"])
@admin_required
def api_kits_eventos_eventos_disponibles():
    """
    Retorna eventos disponibles para dropdown.
    """
    try:
        eventos = EventoCatalogo.query.order_by(EventoCatalogo.evento_tipo_id).all()
        
        eventos_data = [
            {
                "evento_tipo_id": e.evento_tipo_id,
                "nombre": e.nombre,
                "descripcion": e.descripcion
            }
            for e in eventos
        ]
        
        return jsonify({
            "success": True,
            "eventos": eventos_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos/casos-disponibles", methods=["GET"])
@admin_required
def api_kits_eventos_casos_disponibles():
    """
    Retorna casos disponibles para dropdown.
    Query params opcionales:
    - evento_tipo: filtrar por evento_tipo_id (ej: EV-IN-001)
    """
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        
        # Query base
        query = CasoCatalogo.query
        
        # Filtro por evento_tipo
        if evento_tipo:
            query = query.filter_by(evento_tipo_id=evento_tipo)
        
        casos = query.order_by(CasoCatalogo.caso_id).all()
        
        casos_data = [
            {
                "caso_id": c.caso_id,
                "evento_tipo_id": c.evento_tipo_id,
                "nombre": c.nombre,
                "descripcion": c.descripcion
            }
            for c in casos
        ]
        
        return jsonify({
            "success": True,
            "casos": casos_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos/next-id", methods=["GET"])
@admin_required
def api_kits_eventos_next_id():
    """
    Genera el próximo ID disponible para un caso.
    Query param: caso_id (ej: CA-IN-VO-001)
    Retorna: KT-EV-{codigo}-{número} (ej: KT-EV-VO-001)
    
    Extrae el código del caso:
    CA-IN-VO-001 → extrae "VO" (posición 3) → KT-EV-VO-001
    """
    caso_id = request.args.get("caso_id", "").strip()
    
    if not caso_id:
        return jsonify({"success": False, "error": "caso_id requerido"}), 400
    
    try:
        # Extraer código del caso (posición 3)
        # CA-IN-VO-001 → ['CA', 'IN', 'VO', '001'] → 'VO'
        partes = caso_id.split('-')
        if len(partes) < 3:
            return jsonify({"success": False, "error": "Formato de caso_id inválido"}), 400
        
        codigo = partes[2]  # Extraer código del caso (ej: VO, EQ, SA)
        
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
        
        # Buscar el último kit de este código
        pattern = f"KT-EV-{codigo}-%"
        ultimo = Kit.query.filter(
            Kit.kit_id.like(pattern)
        ).order_by(
            Kit.kit_id.desc()
        ).first()
        
        if ultimo:
            partes_kit = ultimo.kit_id.split('-')
            if len(partes_kit) == 4:  # KT-EV-VO-001
                try:
                    numero_actual = int(partes_kit[3])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            siguiente = 1
        
        nuevo_id = f"KT-EV-{codigo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "kit_id": nuevo_id,
            "codigo": codigo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos", methods=["GET"])
@admin_required
def api_kits_eventos_listar():
    """
    Lista kits de tipo 'evento' con sus herramientas.
    Query params opcionales:
    - page: número de página (default 1)
    - per_page: resultados por página (default 50)
    - evento_tipo: filtrar por evento_tipo_id (ej: EV-IN-001)
    - caso: filtrar por caso_id (ej: CA-IN-VO-001)
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        evento_tipo = request.args.get('evento_tipo', '').strip()
        caso = request.args.get('caso', '').strip()
        
        # Query base - solo kits de tipo 'evento'
        query = Kit.query.filter_by(tipo_kit='evento')
        
        # Filtro por caso
        if caso:
            query = query.filter_by(caso_id=caso)
        # Filtro por evento_tipo (requiere join con CasoCatalogo)
        elif evento_tipo:
            query = query.join(CasoCatalogo, Kit.caso_id == CasoCatalogo.caso_id)\
                         .filter(CasoCatalogo.evento_tipo_id == evento_tipo)
        
        # Ordenar y paginar
        query = query.order_by(Kit.kit_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Formatear con herramientas
        kits_data = []
        for k in pagination.items:
            # Obtener herramientas del kit
            detalles = KitDetalle.query.filter_by(kit_id=k.kit_id).all()
            herramientas = [
                {
                    'herramienta_id': d.herramienta_id,
                    'nombre': d.herramienta.nombre if d.herramienta else '',
                    'nota': d.nota
                }
                for d in detalles
            ]
            
            # Obtener info del caso
            caso_info = CasoCatalogo.query.get(k.caso_id) if k.caso_id else None
            evento_info = EventoCatalogo.query.get(caso_info.evento_tipo_id) if caso_info else None
            
            kits_data.append({
                'kit_id': k.kit_id,
                'caso_id': k.caso_id,
                'caso_nombre': caso_info.nombre if caso_info else '',
                'evento_tipo_id': caso_info.evento_tipo_id if caso_info else '',
                'evento_nombre': evento_info.nombre if evento_info else '',
                'nombre': k.nombre,
                'tipo_kit': k.tipo_kit,
                'herramientas': herramientas,
                'cantidad_herramientas': len(herramientas)
            })
        
        return jsonify({
            "success": True,
            "kits": kits_data,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos", methods=["POST"])
@admin_required
def api_kits_eventos_crear():
    """
    Crea un nuevo kit de tipo 'evento'.
    Body JSON:
    {
        "caso_id": "CA-IN-VO-001",
        "nombre": "Kit Vómito",
        "herramientas": ["HE-CE-001", "HE-FI-001"]
    }
    """
    try:
        data = request.get_json()
        
        caso_id = data.get("caso_id", "").strip()
        nombre = data.get("nombre", "").strip()
        herramientas_ids = data.get("herramientas", [])

        # 1. Validar caso_id
        if not caso_id:
            return jsonify({"success": False, "error": "caso_id requerido"}), 400
        
        # 2. Validar que caso existe
        caso = CasoCatalogo.query.get(caso_id)
        if not caso:
            return jsonify({"success": False, "error": f"Caso {caso_id} no encontrado"}), 404
        
        # 3. Validar nombre
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # 4. Validar que tenga al menos 1 herramienta
        if not herramientas_ids or len(herramientas_ids) == 0:
            return jsonify({"success": False, "error": "Debe seleccionar al menos 1 herramienta"}), 400
        
        # 5. Validar que todas las herramientas existan
        for h_id in herramientas_ids:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        
        # 6. Extraer código del caso y generar ID del kit
        # CA-IN-VO-001 → 'VO' → KT-EV-VO-001
        partes = caso_id.split('-')
        if len(partes) < 3:
            return jsonify({"success": False, "error": "Formato de caso_id inválido"}), 400
        
        codigo = partes[2]
        
        pattern = f"KT-EV-{codigo}-%"
        ultimo = Kit.query.filter(
            Kit.kit_id.like(pattern)
        ).order_by(
            Kit.kit_id.desc()
        ).first()
        
        if ultimo:
            partes_kit = ultimo.kit_id.split('-')
            numero_actual = int(partes_kit[3]) if len(partes_kit) == 4 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        kit_id = f"KT-EV-{codigo}-{siguiente:03d}"
        
        # 7. Crear Kit de tipo 'evento'
        nuevo_kit = Kit(
            kit_id=kit_id,
            fraccion_id=None,  # NULL para eventos
            nivel_limpieza_id=None,  # NULL para eventos
            nombre=nombre,
            tipo_kit='evento',
            caso_id=caso_id
        )
        
        db.session.add(nuevo_kit)
        db.session.flush()
        
        # 8. Crear KitDetalle para cada herramienta
        for h_id in herramientas_ids:
            detalle = KitDetalle(
                kit_id=kit_id,
                herramienta_id=h_id,
                nota=nombre
            )
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "kit": {
                "kit_id": nuevo_kit.kit_id,
                "caso_id": nuevo_kit.caso_id,
                "nombre": nuevo_kit.nombre,
                "herramientas": herramientas_ids
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos/<kit_id>", methods=["PUT"])
@admin_required
def api_kits_eventos_editar(kit_id):
    """
    Edita un kit de tipo 'evento' existente.
    Solo permite editar: nombre, herramientas
    NO permite editar: kit_id, caso_id
    
    Body JSON:
    {
        "nombre": "Kit Vómito Mejorado",
        "herramientas": ["HE-CE-001", "HE-FI-002"]
    }
    """
    try:
        kit = Kit.query.get(kit_id)
        
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        
        if kit.tipo_kit != 'evento':
            return jsonify({"success": False, "error": "Este kit no es de tipo evento"}), 400
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nuevas_herramientas = data.get("herramientas", [])
        
        # Validaciones
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        if not nuevas_herramientas or len(nuevas_herramientas) == 0:
            return jsonify({"success": False, "error": "Debe tener al menos 1 herramienta"}), 400
        
        # Validar herramientas
        for h_id in nuevas_herramientas:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        
        # Actualizar Kit
        kit.nombre = nuevo_nombre
        
        # Actualizar herramientas - eliminar todas y recrear
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        
        for h_id in nuevas_herramientas:
            detalle = KitDetalle(
                kit_id=kit_id,
                herramienta_id=h_id,
                nota=nuevo_nombre
            )
            db.session.add(detalle)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "kit": {
                "kit_id": kit.kit_id,
                "caso_id": kit.caso_id,
                "nombre": kit.nombre,
                "herramientas": nuevas_herramientas
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/kits-eventos/<kit_id>", methods=["DELETE"])
@admin_required
def api_kits_eventos_eliminar(kit_id):
    """
    Elimina un kit de tipo 'evento' y sus herramientas.
    """
    try:
        kit = Kit.query.get(kit_id)
        
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        
        if kit.tipo_kit != 'evento':
            return jsonify({"success": False, "error": "Este kit no es de tipo evento"}), 400
        
        # Eliminar KitDetalle primero
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        
        # Eliminar Kit
        db.session.delete(kit)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Kit {kit_id} eliminado correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    

# =========================
# API - FRACCIONES EVENTOS (CRUD)
# =========================

@main_bp.route("/api/fracciones-eventos/eventos-disponibles", methods=["GET"])
@admin_required
def api_fracciones_eventos_eventos_disponibles():
    """
    Retorna eventos disponibles para dropdown.
    """
    try:
        eventos = EventoCatalogo.query.order_by(EventoCatalogo.evento_tipo_id).all()
        
        eventos_data = [
            {
                "evento_tipo_id": e.evento_tipo_id,
                "nombre": e.nombre,
                "descripcion": e.descripcion
            }
            for e in eventos
        ]
        
        return jsonify({
            "success": True,
            "eventos": eventos_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos/codigos-disponibles", methods=["GET"])
@admin_required
def api_fracciones_eventos_codigos_disponibles():
    """
    Extrae códigos únicos de fracciones existentes para un evento.
    Query param: evento_tipo (ej: EV-LI-001)
    
    Retorna códigos únicos con conteo y nombre base.
    """
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        
        if not evento_tipo:
            return jsonify({"success": False, "error": "evento_tipo requerido"}), 400
        
        # Validar que evento existe
        evento = EventoCatalogo.query.get(evento_tipo)
        if not evento:
            return jsonify({"success": False, "error": f"Evento {evento_tipo} no encontrado"}), 404
        
        # Extraer código del evento (EV-LI-001 → LI)
        partes_evento = evento_tipo.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo inválido"}), 400
        
        codigo_evento = partes_evento[1]  # LI, IN, CO, etc.
        
        # Buscar todas las fracciones de este evento
        pattern = f"FR-{codigo_evento}-%"
        fracciones = SopEventoFraccion.query.filter(
            SopEventoFraccion.evento_tipo_id == evento_tipo,
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(SopEventoFraccion.fraccion_evento_id).all()
        
        # Agrupar por código (posición 3: FR-LI-DE-001 → DE)
        codigos_map = {}
        
        for f in fracciones:
            partes = f.fraccion_evento_id.split('-')
            if len(partes) >= 3:
                codigo = partes[2]  # DE, CO, CU, etc.
                
                if codigo not in codigos_map:
                    codigos_map[codigo] = {
                        "codigo": codigo,
                        "nombre_base": f.nombre,  # Usar nombre de la primera fracción
                        "count": 0,
                        "ultima_fraccion": ""
                    }
                
                codigos_map[codigo]["count"] += 1
                codigos_map[codigo]["ultima_fraccion"] = f.fraccion_evento_id
        
        # Convertir a lista ordenada
        codigos_data = sorted(codigos_map.values(), key=lambda x: x["codigo"])
        
        return jsonify({
            "success": True,
            "codigos": codigos_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos/next-id", methods=["GET"])
@admin_required
def api_fracciones_eventos_next_id():
    """
    Genera el próximo ID disponible para una fracción de evento.
    Query params:
    - evento_tipo: evento_tipo_id (ej: EV-LI-001)
    - codigo: código de fracción (ej: DE)
    
    Retorna: FR-{evento}-{codigo}-{número}
    Ejemplo: FR-LI-DE-003
    """
    try:
        evento_tipo = request.args.get("evento_tipo", "").strip()
        codigo = request.args.get("codigo", "").strip().upper()
        
        if not evento_tipo or not codigo:
            return jsonify({"success": False, "error": "evento_tipo y codigo requeridos"}), 400
        
        # Extraer código del evento (EV-LI-001 → LI)
        partes_evento = evento_tipo.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo inválido"}), 400
        
        codigo_evento = partes_evento[1]
        
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
        
        # Buscar la última fracción con este patrón
        pattern = f"FR-{codigo_evento}-{codigo}-%"
        ultima = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(
            SopEventoFraccion.fraccion_evento_id.desc()
        ).first()
        
        if ultima:
            partes = ultima.fraccion_evento_id.split('-')
            if len(partes) == 4:  # FR-LI-DE-001
                try:
                    numero_actual = int(partes[3])
                    siguiente = numero_actual + 1
                except ValueError:
                    siguiente = 1
            else:
                siguiente = 1
        else:
            siguiente = 1
        
        nuevo_id = f"FR-{codigo_evento}-{codigo}-{siguiente:03d}"
        
        return jsonify({
            "success": True,
            "fraccion_evento_id": nuevo_id,
            "codigo_evento": codigo_evento,
            "codigo": codigo,
            "numero": siguiente
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos", methods=["GET"])
@admin_required
def api_fracciones_eventos_listar():
    """
    Lista fracciones de eventos con info de metodología.
    Query params opcionales:
    - evento_tipo: filtrar por evento_tipo_id (ej: EV-LI-001)
    - page: número de página (default 1)
    - per_page: resultados por página (default 50)
    """
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        # Query base
        query = SopEventoFraccion.query
        
        # Filtro por evento
        if evento_tipo:
            query = query.filter_by(evento_tipo_id=evento_tipo)
        
        # Ordenar y paginar
        query = query.order_by(SopEventoFraccion.fraccion_evento_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Formatear datos
        fracciones_data = []
        for f in pagination.items:
            # Extraer código de la fracción (FR-LI-DE-001 → DE)
            partes = f.fraccion_evento_id.split('-')
            codigo = partes[2] if len(partes) >= 3 else ''
            
            # Obtener info de metodología
            metodologia = MetodologiaEventoFraccion.query.filter_by(
                fraccion_evento_id=f.fraccion_evento_id
            ).first()
            
            tiene_metodologia = metodologia is not None
            cantidad_pasos = 0
            
            if metodologia:
                cantidad_pasos = MetodologiaEventoFraccionPaso.query.filter_by(
                    metodologia_fraccion_id=metodologia.metodologia_fraccion_id
                ).count()
            
            # Obtener nombre del evento
            evento_info = EventoCatalogo.query.get(f.evento_tipo_id)
            
            fracciones_data.append({
                'fraccion_evento_id': f.fraccion_evento_id,
                'evento_tipo_id': f.evento_tipo_id,
                'evento_nombre': evento_info.nombre if evento_info else '',
                'codigo': codigo,
                'nombre': f.nombre,
                'descripcion': f.descripcion,
                'tiene_metodologia': tiene_metodologia,
                'cantidad_pasos': cantidad_pasos,
                'metodologia_id': metodologia.metodologia_fraccion_id if metodologia else None
            })
        
        return jsonify({
            "success": True,
            "fracciones": fracciones_data,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": pagination.page
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos", methods=["POST"])
@admin_required
def api_fracciones_eventos_crear():
    """
    Crea una nueva fracción de evento + metodología automática.
    
    Body JSON:
    {
        "evento_tipo_id": "EV-LI-001",
        "codigo": "DE",
        "nombre": "Desmontaje y Segregación",
        "descripcion": "Proceso para..."
    }
    
    Crea automáticamente:
    - SopEventoFraccion (FR-LI-DE-001)
    - MetodologiaEventoFraccion (ME-LI-DE-001) con nombre "Metodología de {nombre}"
    """
    try:
        data = request.get_json()
        
        evento_tipo_id = data.get("evento_tipo_id", "").strip()
        codigo = data.get("codigo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        descripcion = data.get("descripcion", "").strip()
        
        # 1. Validar evento_tipo_id
        if not evento_tipo_id:
            return jsonify({"success": False, "error": "evento_tipo_id requerido"}), 400
        
        evento = EventoCatalogo.query.get(evento_tipo_id)
        if not evento:
            return jsonify({"success": False, "error": f"Evento {evento_tipo_id} no encontrado"}), 404
        
        # 2. Validar código
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Código debe tener 2 caracteres"}), 400
        
        # 3. Validar nombre
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # 4. Extraer código del evento (EV-LI-001 → LI)
        partes_evento = evento_tipo_id.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo_id inválido"}), 400
        
        codigo_evento = partes_evento[1]
        
        # 5. VALIDAR NOMBRE DUPLICADO en el mismo código
        pattern = f"FR-{codigo_evento}-{codigo}-%"
        nombre_existente = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern),
            SopEventoFraccion.nombre == nombre
        ).first()
        
        if nombre_existente:
            return jsonify({
                "success": False,
                "error": f"Ya existe una fracción con el nombre '{nombre}'. Por favor agrega una variación para diferenciarla."
            }), 400
        
        # 6. Generar ID de fracción
        ultima = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(
            SopEventoFraccion.fraccion_evento_id.desc()
        ).first()
        
        if ultima:
            partes = ultima.fraccion_evento_id.split('-')
            numero_actual = int(partes[3]) if len(partes) == 4 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        
        fraccion_evento_id = f"FR-{codigo_evento}-{codigo}-{siguiente:03d}"
        
        # 7. Crear SopEventoFraccion
        nueva_fraccion = SopEventoFraccion(
            fraccion_evento_id=fraccion_evento_id,
            evento_tipo_id=evento_tipo_id,
            nombre=nombre,
            descripcion=descripcion
        )
        
        db.session.add(nueva_fraccion)
        db.session.flush()
        
        # 8. Crear MetodologiaEventoFraccion automáticamente
        metodologia_id = f"ME-{codigo_evento}-{codigo}-{siguiente:03d}"
        nombre_metodologia = f"Metodología de {nombre}"
        
        nueva_metodologia = MetodologiaEventoFraccion(
            metodologia_fraccion_id=metodologia_id,
            fraccion_evento_id=fraccion_evento_id,
            nombre=nombre_metodologia,
            descripcion=descripcion  # Usar misma descripción de la fracción
        )
        
        db.session.add(nueva_metodologia)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_evento_id": nueva_fraccion.fraccion_evento_id,
                "evento_tipo_id": nueva_fraccion.evento_tipo_id,
                "codigo": codigo,
                "nombre": nueva_fraccion.nombre,
                "descripcion": nueva_fraccion.descripcion,
                "metodologia_id": nueva_metodologia.metodologia_fraccion_id
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos/<fraccion_id>", methods=["PUT"])
@admin_required
def api_fracciones_eventos_editar(fraccion_id):
    """
    Edita una fracción de evento existente.
    Solo permite editar: nombre, descripción
    NO permite editar: fraccion_evento_id, evento_tipo_id, código
    
    Body JSON:
    {
        "nombre": "Desmontaje y Segregación Mejorado",
        "descripcion": "Proceso actualizado..."
    }
    
    Actualiza también el nombre de la metodología asociada.
    """
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        data = request.get_json()
        
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_descripcion = data.get("descripcion", "").strip()
        
        # Validar nombre
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        
        # Validar nombre duplicado (excluyendo la fracción actual)
        partes = fraccion_id.split('-')
        if len(partes) >= 3:
            codigo_evento = partes[1]
            codigo = partes[2]
            pattern = f"FR-{codigo_evento}-{codigo}-%"
            
            nombre_existente = SopEventoFraccion.query.filter(
                SopEventoFraccion.fraccion_evento_id.like(pattern),
                SopEventoFraccion.nombre == nuevo_nombre,
                SopEventoFraccion.fraccion_evento_id != fraccion_id
            ).first()
            
            if nombre_existente:
                return jsonify({
                    "success": False,
                    "error": f"Ya existe otra fracción con el nombre '{nuevo_nombre}'. Por favor agrega una variación para diferenciarla."
                }), 400
        
        # Actualizar fracción
        fraccion.nombre = nuevo_nombre
        fraccion.descripcion = nueva_descripcion
        
        # Actualizar nombre de metodología
        metodologia = MetodologiaEventoFraccion.query.filter_by(
            fraccion_evento_id=fraccion_id
        ).first()
        
        if metodologia:
            metodologia.nombre = f"Metodología de {nuevo_nombre}"
            metodologia.descripcion = nueva_descripcion
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_evento_id": fraccion.fraccion_evento_id,
                "evento_tipo_id": fraccion.evento_tipo_id,
                "nombre": fraccion.nombre,
                "descripcion": fraccion.descripcion
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/fracciones-eventos/<fraccion_id>", methods=["DELETE"])
@admin_required
def api_fracciones_eventos_eliminar(fraccion_id):
    """
    Elimina una fracción de evento.
    La metodología se elimina automáticamente en cascada (definido en models).
    """
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        
        if not fraccion:
            return jsonify({"success": False, "error": "Fracción no encontrada"}), 404
        
        # Validar que no esté en uso en SopEventoDetalle
        en_uso = SopEventoDetalle.query.filter_by(fraccion_evento_id=fraccion_id).count()
        
        if en_uso > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta fracción está siendo usada en {en_uso} SOP(s) de eventos."
            }), 400
        
        # Eliminar fracción (metodología se elimina en cascada)
        db.session.delete(fraccion)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Fracción {fraccion_id} eliminada correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/catalogos/fracciones-eventos")
@admin_required
def catalogos_fracciones_eventos():
    return render_template("catalogos/eventos/fracciones_eventos.html")


# =========================
# METODOLOGÍAS EVENTOS - DETALLE Y PASOS
# =========================

@main_bp.route("/catalogos/metodologias-eventos/<metodologia_id>")
@admin_required
def metodologia_evento_detalle(metodologia_id):
    """Página de edición de pasos de una metodología de evento"""
    
    # Validar que la metodología existe
    metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)
    
    if not metodologia:
        flash(f"Metodología {metodologia_id} no encontrada", "error")
        return redirect(url_for('main.catalogos_fracciones_eventos'))
    
    # Obtener fracción asociada
    fraccion = metodologia.fraccion
    
    # Obtener evento
    evento = EventoCatalogo.query.get(fraccion.evento_tipo_id) if fraccion else None
    
    return render_template(
        "catalogos/eventos/metodologia_evento_detalle.html",
        metodologia=metodologia,
        fraccion=fraccion,
        evento=evento,
        hide_nav=True
    )


@main_bp.route("/api/metodologias-eventos/<metodologia_id>", methods=["GET"])
@admin_required
def api_metodologia_evento_get(metodologia_id):
    """
    Obtiene los datos de una metodología de evento con sus pasos.
    
    Returns:
    {
        "success": true,
        "metodologia": {
            "metodologia_fraccion_id": "ME-LI-DE-001",
            "fraccion_evento_id": "FR-LI-DE-001",
            "nombre": "Metodología de...",
            "descripcion": "...",
            "pasos": [
                {"numero_paso": 1, "descripcion": "..."},
                {"numero_paso": 2, "descripcion": "..."}
            ]
        },
        "fraccion": {...},
        "evento": {...}
    }
    """
    try:
        # Validar metodología
        metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)
        if not metodologia:
            return jsonify({"success": False, "error": "Metodología no encontrada"}), 404
        
        # Obtener pasos ordenados
        pasos = []
        for paso in metodologia.pasos:
            pasos.append({
                "numero_paso": paso.numero_paso,
                "descripcion": paso.descripcion
            })
        
        # Obtener fracción
        fraccion = metodologia.fraccion
        
        # Obtener evento
        evento = EventoCatalogo.query.get(fraccion.evento_tipo_id) if fraccion else None
        
        return jsonify({
            "success": True,
            "metodologia": {
                "metodologia_fraccion_id": metodologia.metodologia_fraccion_id,
                "fraccion_evento_id": metodologia.fraccion_evento_id,
                "nombre": metodologia.nombre,
                "descripcion": metodologia.descripcion,
                "pasos": pasos
            },
            "fraccion": {
                "fraccion_evento_id": fraccion.fraccion_evento_id,
                "nombre": fraccion.nombre,
                "descripcion": fraccion.descripcion,
                "evento_tipo_id": fraccion.evento_tipo_id
            } if fraccion else None,
            "evento": {
                "evento_tipo_id": evento.evento_tipo_id,
                "nombre": evento.nombre
            } if evento else None
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/metodologias-eventos/<metodologia_id>/pasos", methods=["POST"])
@admin_required
def api_metodologia_evento_save_pasos(metodologia_id):
    """
    Guarda/actualiza los pasos de una metodología de evento.
    
    Body JSON:
    {
        "pasos": [
            {"numero_paso": 1, "descripcion": "Paso 1..."},
            {"numero_paso": 2, "descripcion": "Paso 2..."}
        ]
    }
    
    Proceso:
    1. Valida que la metodología existe
    2. Borra pasos viejos
    3. Inserta pasos nuevos
    4. Valida que haya al menos 1 paso
    """
    try:
        # Validar metodología
        metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)
        if not metodologia:
            return jsonify({"success": False, "error": "Metodología no encontrada"}), 404
        
        # Obtener pasos del body
        data = request.get_json()
        pasos = data.get("pasos", [])
        
        # Validar que haya al menos 1 paso
        if len(pasos) == 0:
            return jsonify({"success": False, "error": "Debe haber al menos 1 paso"}), 400
        
        # Validar que todos los pasos tengan descripción
        for paso in pasos:
            if not paso.get("descripcion", "").strip():
                return jsonify({"success": False, "error": "Todos los pasos deben tener descripción"}), 400
        
        # Borrar pasos viejos
        MetodologiaEventoFraccionPaso.query.filter_by(
            metodologia_fraccion_id=metodologia_id
        ).delete()
        
        # Insertar pasos nuevos
        for paso in pasos:
            nuevo_paso = MetodologiaEventoFraccionPaso(
                metodologia_fraccion_id=metodologia_id,
                numero_paso=paso["numero_paso"],
                descripcion=paso["descripcion"].strip()
            )
            db.session.add(nuevo_paso)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "metodologia_fraccion_id": metodologia_id,
            "total_pasos": len(pasos),
            "message": f"Metodología {metodologia_id} guardada correctamente con {len(pasos)} paso(s)"
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500