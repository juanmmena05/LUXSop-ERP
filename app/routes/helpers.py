# helpers.py - Funciones compartidas entre blueprints
import unicodedata
from typing import Optional
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from functools import wraps

from flask import abort
from flask_login import login_required, current_user

from ..extensions import db
from ..models import (
    Area, SubArea, SOP, NivelLimpieza, Personal,
    Fraccion, Metodologia, MetodologiaBase, MetodologiaBasePaso,
    SopFraccion, SopFraccionDetalle,
    LanzamientoSemana, LanzamientoDia, LanzamientoTarea,
    AsignacionPersonal,
    PlantillaSemanal, PlantillaItem, PlantillaSemanaAplicada,
    TareaCheck,
    EventoCatalogo, CasoCatalogo, SopEventoFraccion,
    MetodologiaEventoFraccion, MetodologiaEventoFraccionPaso,
    SopEvento, SopEventoDetalle,
    Elemento, ElementoSet, ElementoDetalle,
    Kit, KitDetalle, Herramienta,
    Receta, RecetaDetalle, Quimico, Consumo,
)

import os
import shutil

# =========================
# Zona Horaria México
# =========================
MEXICO_TZ = ZoneInfo('America/Mexico_City')

def now_cdmx():
    """Retorna datetime actual en hora de México (naive, sin tzinfo para BD)"""
    return datetime.now(MEXICO_TZ).replace(tzinfo=None)

def today_cdmx():
    """Retorna date actual en zona horaria de México"""
    return datetime.now(MEXICO_TZ).date()

# =========================
# Decoradores
# =========================
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
        {'tipo_tarea': 'inicio', 'orden': -3, 'sop_evento_id': None, 'es_arrastrable': False},
        {'tipo_tarea': 'receso', 'orden': 50, 'sop_evento_id': None, 'es_arrastrable': True},
        {'tipo_tarea': 'limpieza_equipo', 'orden': 999, 'sop_evento_id': 'SP-LI-EQ-001', 'es_arrastrable': False}
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
    """Verifica si un operario tiene tareas fijas en un día. Si NO las tiene, las crea."""
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


def set_plantilla_activa(lunes: date, plantilla_id: int = None):
    """Marca o desmarca la plantilla activa de una semana"""
    marca = PlantillaSemanaAplicada.query.get(lunes)

    if plantilla_id is None:
        if marca:
            db.session.delete(marca)
    else:
        if marca:
            marca.plantilla_id = plantilla_id
            marca.aplicada_en = now_cdmx()
        else:
            marca = PlantillaSemanaAplicada(
                semana_lunes=lunes,
                plantilla_id=plantilla_id,
                aplicada_en=now_cdmx()
            )
            db.session.add(marca)

    db.session.commit()


# =========================
# Helpers Nivel Limpieza
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
    if x in {"4", "extraordinario", "extraordinaria"}:
        return "extraordinario"
    return None


def nivel_to_id(s: Optional[str]) -> Optional[int]:
    x = canon_nivel(s or "")
    return {"basica": 1, "media": 2, "profundo": 3, "extraordinario": 4}.get(x)


# =========================
# Helpers de Plantilla
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
    asegurar_tareas_fijas(dia.dia_id, personal_id)


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

    dias_map = {}
    fechas_necesarias = set()

    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        fechas_necesarias.add(fecha_dest)

    semana = LanzamientoSemana.query.filter_by(fecha_inicio=destino_lunes).first()
    if not semana:
        semana = LanzamientoSemana(
            nombre=f"Semana {destino_lunes.isocalendar()[1]}",
            fecha_inicio=destino_lunes
        )
        db.session.add(semana)
        db.session.flush()

    dias_existentes = LanzamientoDia.query.filter(
        LanzamientoDia.fecha.in_(fechas_necesarias),
        LanzamientoDia.semana_id == semana.semana_id
    ).all()

    for dia in dias_existentes:
        dias_map[dia.fecha] = dia.dia_id

    for fecha in fechas_necesarias:
        if fecha not in dias_map:
            nuevo_dia = LanzamientoDia(semana_id=semana.semana_id, fecha=fecha)
            db.session.add(nuevo_dia)
            db.session.flush()
            dias_map[fecha] = nuevo_dia.dia_id

    dia_ids = list(dias_map.values())
    tareas_existentes = set()

    if dia_ids:
        tareas_actuales = db.session.query(
            LanzamientoTarea.dia_id,
            LanzamientoTarea.subarea_id,
            LanzamientoTarea.sop_id
        ).filter(LanzamientoTarea.dia_id.in_(dia_ids)).all()

        for t in tareas_actuales:
            tareas_existentes.add((t.dia_id, t.subarea_id, t.sop_id))

    subareas_sin_sop = [it.subarea_id for it in plantilla.items if not getattr(it, 'sop_id', None)]
    sops_map = {}

    if subareas_sin_sop:
        sops = SOP.query.filter(
            SOP.subarea_id.in_(subareas_sin_sop),
            SOP.tipo_sop == "regular"
        ).all()
        for sop in sops:
            sops_map[sop.subarea_id] = sop.sop_id

    operarios_por_dia = {}
    tareas_a_insertar = []

    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        dia_id = dias_map[fecha_dest]

        sop_id = getattr(it, 'sop_id', None)
        if not sop_id:
            sop_id = sops_map.get(it.subarea_id)

        es_adicional = getattr(it, 'es_adicional', False)

        if not (es_adicional and sop_id and '-C' in sop_id):
            if (dia_id, it.subarea_id, sop_id) in tareas_existentes:
                continue

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

        if dia_id not in operarios_por_dia:
            operarios_por_dia[dia_id] = set()
        operarios_por_dia[dia_id].add(it.personal_id)

    if tareas_a_insertar:
        db.session.bulk_save_objects(tareas_a_insertar)

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
    if not c:
        return "No aplica"

    v = getattr(c, "valor", None)
    u = getattr(c, "unidad", None)
    regla = getattr(c, "regla", None)

    left = None
    if v is not None and u:
        left = f"{v:g} {u}".strip()

    if regla:
        r = str(regla).strip()
        if not r.startswith("="):
            r = f"= {r}"
        return f"{left} {r}".strip() if left else r

    return left or "No aplica"


def fmt_herramientas(kit) -> list[str]:
    if not kit:
        return []
    dets = getattr(kit, "detalles", None) or []
    return [
        kd.herramienta.descripcion
        for kd in dets
        if getattr(kd, "herramienta", None) and getattr(kd.herramienta, "descripcion", None)
    ]


def fmt_herramientas_list(kit) -> list[str]:
    items = fmt_herramientas(kit)
    return items if items else ["No aplica"]


def fmt_receta(receta) -> str:
    if not receta:
        return "No aplica"

    dets = getattr(receta, "detalles", None) or []
    if not dets:
        return na(getattr(receta, "nombre", None))

    partes = []
    for d in dets:
        if getattr(d, "dosis", None) is not None and getattr(d, "unidad_dosis", None):
            partes.append(f"{d.dosis:g} {d.unidad_dosis}".strip())
        if getattr(d, "volumen_base", None) is not None and getattr(d, "unidad_volumen", None):
            partes.append(f"{d.volumen_base:g} {d.unidad_volumen}".strip())

    s = " + ".join([p for p in partes if p])
    return s.strip() if s.strip() else na(getattr(receta, "nombre", None))


def fmt_quimico_y_receta(receta) -> tuple[str, str]:
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
    receta_str = fmt_receta(receta)

    return quimico_str, receta_str


# Cache
_cache_timestamp = {}

def get_cached_or_query(cache_key, query_func, timeout_minutes=5):
    now = now_cdmx()

    if cache_key in _cache_timestamp:
        cached_time, cached_data = _cache_timestamp[cache_key]
        if now - cached_time < timedelta(minutes=timeout_minutes):
            return cached_data

    data = query_func()
    _cache_timestamp[cache_key] = (now, data)
    return data


def get_all_areas():
    return get_cached_or_query(
        'areas_list',
        lambda: Area.query.order_by(Area.orden_area).all(),
        timeout_minutes=10
    )


# =========================
# Helper calcular tiempo tarea
# =========================
def calcular_tiempo_tarea(tarea):
    """Calcula el tiempo estimado de una tarea según su tipo."""
    if tarea.tipo_tarea == 'inicio':
        return 0
    elif tarea.tipo_tarea == 'receso':
        return 45
    elif tarea.tipo_tarea == 'limpieza_equipo':
        if tarea.sop_evento and tarea.sop_evento.detalles:
            return sum(detalle.tiempo_estimado for detalle in tarea.sop_evento.detalles)
        return 60
    elif tarea.tipo_tarea == 'evento':
        if tarea.sop_evento and tarea.sop_evento.detalles:
            return sum(detalle.tiempo_estimado for detalle in tarea.sop_evento.detalles)
        return 0
    elif tarea.tipo_tarea == 'sop':
        if not tarea.sop or not tarea.nivel_limpieza_asignado:
            return 0

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

    return 0
