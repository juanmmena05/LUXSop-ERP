# routes_v2.py
import unicodedata
from typing import Optional
from datetime import datetime, date, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, make_response, abort, session
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_

from flask_login import login_user, logout_user, login_required, current_user

from .models import User
from functools import wraps

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

# --- Helper: set etiqueta plantilla activa para una semana ---
def set_plantilla_activa(lunes_semana: date, plantilla_id: Optional[int]):
    fila = PlantillaSemanaAplicada.query.get(lunes_semana)
    if not fila:
        fila = PlantillaSemanaAplicada(semana_lunes=lunes_semana, plantilla_id=plantilla_id)
        db.session.add(fila)
    else:
        fila.plantilla_id = plantilla_id
        fila.aplicada_en = datetime.utcnow()
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
    if overwrite:
        borrar_asignaciones_semana(destino_lunes)

    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        
        # ✅ Copiar sop_id y es_adicional desde PlantillaItem
        sop_id = getattr(it, 'sop_id', None)
        es_adicional = getattr(it, 'es_adicional', False)
        
        # Si no tiene sop_id (items viejos), calcularlo
        if not sop_id:
            sop = SOP.query.filter_by(subarea_id=it.subarea_id, tipo_sop="regular").first()
            sop_id = sop.sop_id if sop else None
        
        dia = upsert_dia(fecha_dest)
        
        # Verificar si ya existe (para evitar duplicados)
        if es_adicional and sop_id and '-C' in sop_id:
            # Consecuentes: no validar duplicados
            pass
        else:
            existe = LanzamientoTarea.query.filter_by(
                dia_id=dia.dia_id,
                subarea_id=it.subarea_id,
                sop_id=sop_id
            ).first()
            if existe:
                continue
        
        t = LanzamientoTarea(
            dia_id=dia.dia_id,
            personal_id=it.personal_id,
            area_id=it.area_id,
            subarea_id=it.subarea_id,
            nivel_limpieza_asignado=canon_nivel(it.nivel_limpieza_asignado) or "basica",
            sop_id=sop_id,
            es_adicional=es_adicional,
            orden=it.orden or 0
        )
        db.session.add(t)
    
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



# =========================
# HOME (panel semanal)
# =========================
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
# INIT DB
# =========================
@main_bp.route("/initdb")
@admin_required
def initdb():
    db.create_all()
    return "Base de datos creada (tablas listas)."

# =========================
# ÁREAS
# =========================
@main_bp.route("/areas")
@admin_required
def listar_areas():
    areas = Area.query.all()
    return render_template("areas_list.html", areas=areas)

@main_bp.route("/areas/nueva", methods=["GET", "POST"])
@admin_required
def nueva_area():
    if request.method == "POST":
        area_id = request.form.get("area_id")
        area_nombre = request.form.get("area_nombre")
        tipo_area = request.form.get("tipo_area")
        cantidad_subareas = int(request.form.get("cantidad_subareas") or 0)

        db.session.add(Area(
            area_id=area_id,
            area_nombre=area_nombre,
            tipo_area=tipo_area,
            cantidad_subareas=cantidad_subareas,
        ))
        db.session.commit()
        return redirect(url_for("main.listar_areas"))
    return render_template("areas_form.html")

# =========================
# SUBÁREAS (compat con templates viejos)
# =========================
@main_bp.route("/subareas")
@admin_required
def listar_subareas():
    # Tu template subareas_list.html pide:
    # s.nivel_limpieza y s.tiempo_total_subarea, que ya no existen en SubArea v2.
    # Para no romper HTML, armamos una "vista" (dicts con dot-access).
    subareas = (
        SubArea.query
        .options(joinedload(SubArea.area))
        .order_by(SubArea.orden_subarea.asc())
        .all()
    )

    subareas_view = []
    for s in subareas:
        # tiempo_total_subarea: lo calculamos con SOP si existe (nivel base no aplica aquí)
        tiempo_total = None
        sop = SOP.query.filter_by(subarea_id=s.subarea_id).first()
        if sop:
            # suma TIEMPOS de PROFUNDO como default (3) para tener algo que mostrar
            tiempo_total = 0.0
            for sf in sop.sop_fracciones:
                sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == 3), None)
                if sd and sd.tiempo_unitario_min is not None:
                    tiempo_total += float(sd.tiempo_unitario_min)

        subareas_view.append({
            "subarea_id": s.subarea_id,
            "subarea_nombre": s.subarea_nombre,
            "area_id": s.area_id,
            "area": s.area,
            "superficie_subarea": s.superficie_subarea,
            "frecuencia": s.frecuencia,

            # Compat template viejo:
            "nivel_limpieza": None,
            "tiempo_total_subarea": round(tiempo_total, 2) if tiempo_total is not None else None,
        })

    return render_template("subareas_list.html", subareas=subareas_view)

@main_bp.route("/subareas/nueva", methods=["GET", "POST"])
@admin_required
def nueva_subarea():
    areas = Area.query.all()
    if request.method == "POST":
        subarea_id = request.form.get("subarea_id")
        area_id = request.form.get("area_id")
        subarea_nombre = request.form.get("subarea_nombre")
        superficie_subarea = float(request.form.get("superficie_subarea") or 0)
        frecuencia = float(request.form.get("frecuencia") or 0)

        # Campos que vienen en tu template viejo pero ya no existen:
        # nivel_limpieza = request.form.get("nivel_limpieza")  # ignorado
        # tiempo_total_subarea = request.form.get("tiempo_total_subarea")  # ignorado

        db.session.add(SubArea(
            subarea_id=subarea_id,
            area_id=area_id,
            subarea_nombre=subarea_nombre,
            superficie_subarea=superficie_subarea,
            frecuencia=frecuencia,
        ))
        db.session.commit()
        return redirect(url_for("main.listar_subareas"))
    return render_template("subareas_form.html", areas=areas)

# =========================
# PERSONAL
# =========================
@main_bp.route("/personal/nuevo", methods=["GET", "POST"])
@admin_required
def personal_nuevo():
    if request.method == "POST":
        personal_id = request.form.get("personal_id")
        nombre = request.form.get("nombre")

        db.session.add(Personal(personal_id=personal_id, nombre=nombre))
        db.session.commit()
        return redirect(url_for("main.asignar_ruta", personal_id=personal_id))
    return render_template("personal_form.html")

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
    tarea = LanzamientoTarea.query.get_or_404(tarea_id)
    db.session.delete(tarea)
    db.session.commit()
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
            es_adicional=es_adicional
        )
        db.session.add(t)
        db.session.commit()
        
        return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

    # ========== GET ==========
    tareas_del_dia = LanzamientoTarea.query.filter(LanzamientoTarea.dia_id == dia.dia_id).all()
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
def calcular_tiempo_tarea(tarea) -> float:
    """
    Tiempo total = suma de SopFraccionDetalle.tiempo_unitario_min
    filtrado por el nivel asignado.
    
    ✅ CORREGIDO: Usa tarea.sop_id en lugar de buscar por subarea_id
    """
    nivel_text = canon_nivel(tarea.nivel_limpieza_asignado) or "basica"
    nivel_id = nivel_to_id(nivel_text) or 1

    # ✅ Usar sop_id de la tarea directamente
    sop_id = getattr(tarea, 'sop_id', None)
    
    if not sop_id:
        # Fallback para tareas antiguas sin sop_id
        subarea = getattr(tarea, "subarea", None) or SubArea.query.get(tarea.subarea_id)
        if not subarea:
            return 0.0
        sop = SOP.query.filter_by(subarea_id=subarea.subarea_id, tipo_sop="regular").first()
        if not sop:
            return 0.0
        sop_id = sop.sop_id

    # Precarga fracciones/detalles
    sop_full = (
        SOP.query.options(
            joinedload(SOP.sop_fracciones)
                .joinedload(SopFraccion.detalles),
        )
        .filter_by(sop_id=sop_id)
        .first()
    )
    if not sop_full:
        return 0.0

    total = 0.0
    for sf in sop_full.sop_fracciones or []:
        sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == nivel_id), None)
        if sd and sd.tiempo_unitario_min is not None:
            total += float(sd.tiempo_unitario_min)

    return round(total, 2)


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
    
    # Determinar si el usuario puede hacer checks (solo operativo, solo hoy, solo sus tareas)
    puede_hacer_check = False
    es_hoy = (fecha == date.today().strftime("%Y-%m-%d"))
    
    if current_user.role != "admin":
        if current_user.personal_id != personal_id:
            abort(403)
        if not es_hoy:
            abort(403)
        puede_hacer_check = True  # Operativo viendo su reporte de hoy
    
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return f"No existe un registro de día para la fecha {fecha}.", 404

    tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id, personal_id=personal_id).all()
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

    persona = getattr(tareas[0], "personal", None) or Personal.query.filter_by(personal_id=personal_id).first()
    detalles = []

    for t in tareas:
        area = t.area
        subarea = t.subarea
        if not area or not subarea:
            continue

        # ✅ CAMBIO CRÍTICO: Usar sop_id de la tarea
        sop_id = getattr(t, 'sop_id', None)
        print(f"DEBUG: tarea_id={t.tarea_id}, sop_id de tarea={sop_id}")  # ← AGREGAR
        if sop_id:
            sop = SOP.query.filter_by(sop_id=sop_id).first()
        else:
            # Fallback para tareas antiguas sin sop_id
            sop = SOP.query.filter_by(subarea_id=subarea.subarea_id, tipo_sop="regular").first()
        
        if not sop:
            continue

        nivel_asignado = canon_nivel(t.nivel_limpieza_asignado)
        nivel_id = nivel_to_id(nivel_asignado)
        if not nivel_id:
            continue

        sop_full = (
            SOP.query.options(
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.fraccion),

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
            consumo_sd = getattr(sd, "consumo", None)

            tiempo_min = float(sd.tiempo_unitario_min) if sd.tiempo_unitario_min is not None else None

            if tiempo_min is not None:
                tiempo_total_min += tiempo_min

            tabla = None

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
                "descripcion": metodologia.descripcion or "",
                "nivel_limpieza": nivel_asignado,
                "tiempo_min": round(tiempo_min, 2) if tiempo_min is not None else None,
                "metodologia": metodologia,
                "tabla": tabla,
                "observacion_critica": (fr.nota_tecnica if fr else None),
            })

        detalles.append({
            "tarea_id": t.tarea_id,
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "tiempo_total_min": round(tiempo_total_min, 2),
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas,
            "orden": t.orden if t.orden is not None else 0,
            "orden_area": area.orden_area if area.orden_area is not None else 9999,
            "orden_subarea": subarea.orden_subarea if subarea.orden_subarea is not None else 9999,
            # ✅ NUEVOS CAMPOS para el template
            "es_adicional": getattr(t, 'es_adicional', False),
            "sop_id": sop_id,
        })

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
# UI: GET formulario aplicar plantilla
# =========================
@main_bp.route("/plantillas/aplicar")
@admin_required
def plantillas_aplicar_form():
    hoy = date.today()
    lunes_destino = get_monday(hoy)
    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    lunes_anterior = lunes_destino - timedelta(days=7)
    return render_template(
        "plantillas_aplicar.html",
        lunes_destino=lunes_destino,
        lunes_anterior=lunes_anterior,
        plantillas=plantillas
    )

# =========================
# POST aplicar plantilla
# =========================
@main_bp.route("/plantillas/aplicar", methods=["POST"])
@admin_required
def plantillas_aplicar_post():
    modo = request.form.get("modo")  # ruta_base | semana | plantilla
    overwrite = request.form.get("overwrite") == "on"
    lunes_destino_str = request.form.get("lunes_destino")
    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()

    if modo == "ruta_base":
        aplicar_ruta_base_personal(lunes_destino, overwrite)
    elif modo == "semana":
        lunes_origen_str = request.form.get("lunes_origen")
        lunes_origen = datetime.strptime(lunes_origen_str, "%Y-%m-%d").date()
        aplicar_desde_semana(lunes_origen, lunes_destino, overwrite)
    elif modo == "plantilla":
        plantilla_id = int(request.form.get("plantilla_id"))
        aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite)

    return redirect(url_for("main.home"))

# =========================
# CRUD mínimo: guardar semana como plantilla (original)
# =========================
@main_bp.route("/plantillas/guardar", methods=["POST"])
@admin_required
def guardar_semana_como_plantilla():
    nombre = request.form.get("nombre")
    lunes_ref = datetime.strptime(request.form.get("lunes_ref"), "%Y-%m-%d").date()

    if not nombre:
        return "Nombre requerido", 400
    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        return "Ya existe una plantilla con ese nombre.", 400

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
    return redirect(url_for("main.plantillas_aplicar_form"))

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
    lunes_destino_str = request.form.get("lunes_destino")
    plantilla_id_str = request.form.get("plantilla_id")  # none | id

    if not lunes_destino_str or plantilla_id_str is None:
        return "Faltan datos", 400

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()

    # 1) Ninguna: vaciar semana y quitar etiqueta
    if plantilla_id_str == "none":
        borrar_asignaciones_semana(lunes_destino)
        set_plantilla_activa(lunes_destino, None)
        flash("Semana vaciada. Plantilla activa: Ninguna.", "success")
        return redirect(url_for("main.home"))

    # 2) Plantilla: reemplazo total
    plantilla_id = int(plantilla_id_str)

    borrar_asignaciones_semana(lunes_destino)
    aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite=False)
    set_plantilla_activa(lunes_destino, plantilla_id)

    flash("Plantilla aplicada. La semana fue reemplazada por completo.", "success")
    return redirect(url_for("main.home"))

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
# Ordenar Elementos Plantilla
# =========================
@main_bp.route("/elemento_set/<elemento_set_id>/orden", methods=["GET", "POST"])
@admin_required
def ordenar_elementoset(elemento_set_id):
    es = (
        ElementoSet.query.options(
            joinedload(ElementoSet.detalles).joinedload(ElementoDetalle.elemento)
        )
        .filter_by(elemento_set_id=elemento_set_id)
        .first()
    )
    if not es:
        abort(404)

    if request.method == "POST":
        for ed in es.detalles or []:
            key = f"orden_{ed.elemento_id}"
            val = (request.form.get(key) or "").strip()
            if val.isdigit():
                ed.orden = int(val)
        db.session.commit()
        flash("✅ Orden actualizado.", "success")
        return redirect(url_for("main.ordenar_elementoset", elemento_set_id=elemento_set_id))

    detalles = sorted((es.detalles or []), key=lambda x: (x.orden or 9999, x.elemento_id))
    return render_template("elementoset_orden.html", es=es, detalles=detalles)


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
# REMOVER plantilla activa (NO borra tareas)
# =========================
@main_bp.route("/plantillas/remover_semana", methods=["POST"])
@admin_required
def remover_plantilla_semana():
    lunes_destino_str = request.form.get("lunes_destino")
    if not lunes_destino_str:
        return "Falta lunes_destino", 400

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()

    # Solo desvincula plantilla activa, NO toca LanzamientoTarea
    set_plantilla_activa(lunes_destino, None)
    flash("Plantilla removida (no se borraron tareas).", "success")
    return redirect(url_for("main.home"))


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
    area_id = (request.args.get("area_id") or "").strip()
    subarea_id = (request.args.get("subarea_id") or "").strip()
    tipo_sop = (request.args.get("tipo_sop") or "regular").strip()  # ← NUEVO

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
        # ← MODIFICADO: buscar por subarea_id Y tipo_sop
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

    return render_template(
        "sop_panel.html",
        areas=areas,
        subareas=subareas,
        area_id=area_id,
        subarea_id=subarea_id,
        sop=sop,
        has_fracciones=has_fracciones,
        has_nivel=has_nivel,
        nivel=nivel,
        nivel_id=nivel_id,
        tipo_sop=tipo_sop,  # ← NUEVO
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

    # Obtener grupo_area del área padre
    grupo_area = subarea.area.grupo_area if subarea.area else None

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

    # Fracciones disponibles: filtrar por grupo_area Y que tengan metodología para ese nivel
    fracciones_query = (
        Fraccion.query
        .join(Metodologia, Metodologia.fraccion_id == Fraccion.fraccion_id)
        .filter(Metodologia.nivel_limpieza_id.in_(niveles_validos))  # ← Usar IN
        .distinct()
    )
        
    # Filtrar por grupo_area si existe
    if grupo_area:
        fracciones_query = fracciones_query.filter(Fraccion.grupo_area == grupo_area)
    
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
                # borrar detalle de ESTE nivel
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
        tareas = (
            LanzamientoTarea.query
            .filter_by(dia_id=dia.dia_id, personal_id=current_user.personal_id)
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