# routes_v2.py
import unicodedata
from typing import Optional
from datetime import datetime, date, timedelta

import pdfkit
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, make_response
from sqlalchemy.orm import joinedload

from .extensions import db
from .models import (
    # Core
    Area, SubArea, SOP, NivelLimpieza, Personal,

    # Catalogos / armado SOP
    Fraccion, Metodologia, MetodologiaPasos,
    SopFraccion, SopFraccionDetalle,

    # Planeacion
    LanzamientoSemana, LanzamientoDia, LanzamientoTarea,
    AsignacionPersonal,
    PlantillaSemanal, PlantillaItem, PlantillaSemanaAplicada,

    # Recursos / elementos
    Elemento, ElementoSet, ElementoDetalle,
    Kit, KitDetalle, Herramienta,
    Receta, RecetaDetalle, Quimico, Consumo,
)

# =========================
# Helpers de PDF
# =========================
WKHTMLTOPDF_CMD = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_CMD)

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
    return None

def nivel_to_id(s: Optional[str]) -> Optional[int]:
    x = canon_nivel(s or "")
    return {"basica": 1, "media": 2, "profundo": 3}.get(x)

main_bp = Blueprint("main", __name__)


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


def fmt_herramientas(kit) -> str:
    if not kit:
        return "No aplica"
    dets = getattr(kit, "detalles", None) or []
    nombres = [kd.herramienta.nombre for kd in dets if getattr(kd, "herramienta", None)]
    return " - ".join(nombres) if nombres else na(getattr(kit, "nombre", None))


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
@main_bp.route("/")
def home():
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
        plantilla_activa=plantilla_activa
    )

# =========================
# INIT DB
# =========================
@main_bp.route("/initdb")
def initdb():
    db.create_all()
    return "Base de datos creada (tablas listas)."

# =========================
# ÁREAS
# =========================
@main_bp.route("/areas")
def listar_areas():
    areas = Area.query.all()
    return render_template("areas_list.html", areas=areas)

@main_bp.route("/areas/nueva", methods=["GET", "POST"])
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
        if not nivel_limpieza_asignado:
            flash("Nivel de limpieza inválido.", "warning")
            return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

        existe_misma_subarea = LanzamientoTarea.query.filter_by(
            dia_id=dia.dia_id,
            subarea_id=subarea_id
        ).first()
        if existe_misma_subarea:
            flash("Esa subárea ya tiene una tarea asignada en este día.", "warning")
            return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

        db.session.add(LanzamientoTarea(
            dia_id=dia.dia_id,
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado
        ))
        db.session.commit()
        return redirect(url_for("main.plan_dia_asignar", fecha=fecha))

    tareas_del_dia = LanzamientoTarea.query.filter(LanzamientoTarea.dia_id == dia.dia_id).all()
    tiempos_por_tarea = {t.tarea_id: calcular_tiempo_tarea(t) for t in tareas_del_dia}

    tareas_por_persona = {}
    for t in tareas_del_dia:
        key = t.personal_id
        if key not in tareas_por_persona:
            persona = getattr(t, "personal", None) or Personal.query.filter_by(personal_id=key).first()
            tareas_por_persona[key] = {"persona": persona, "subtareas": []}
        tareas_por_persona[key]["subtareas"].append(t)

    asignadas_ids = {t.subarea_id for t in tareas_del_dia}

    return render_template(
        "plan_dia_form.html",
        fecha=fecha_obj,
        personal_list=personal_list,
        areas_list=areas_list,
        subareas_list=subareas_list,
        tareas_del_dia=tareas_del_dia,
        tareas_por_persona=tareas_por_persona,
        tiempos_por_tarea=tiempos_por_tarea,
        asignadas_ids=asignadas_ids
    )

# =========================
# Calcular Tiempo Tarea (v2)
# =========================
def calcular_tiempo_tarea(tarea) -> float:
    """
    Tiempo total = suma de SopFraccionDetalle.tiempo_unitario_min
    filtrado por el nivel asignado.
    """
    nivel_text = canon_nivel(tarea.nivel_limpieza_asignado) or "basica"
    nivel_id = nivel_to_id(nivel_text) or 1

    subarea = getattr(tarea, "subarea", None) or SubArea.query.get(tarea.subarea_id)
    if not subarea:
        return 0.0

    sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first()
    if not sop:
        return 0.0

    # Precarga fracciones/detalles
    sop_full = (
        SOP.query.options(
            joinedload(SOP.sop_fracciones)
                .joinedload(SopFraccion.detalles),
        )
        .filter_by(sop_id=sop.sop_id)
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

    return render_template("ruta_dia.html", fecha=fecha_obj, personas=personas)

# =========================
# REPORTE (micro) — HTML reporte_personal.html
# =========================
@main_bp.route("/reporte/<fecha>/<personal_id>")
def reporte_persona_dia(fecha, personal_id):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

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

        # Cargar SOP con toda la cadena necesaria (incluye consumo y detalles por elemento)
        sop_full = (
            SOP.query.options(
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.fraccion),

                # Detalle sin elementos: kit/herramientas
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                # Detalle sin elementos: receta/químicos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                # Detalle sin elementos: consumo
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.consumo),

                # Detalle con elementos: elemento_set -> elemento
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.elemento),

                # Detalle con elementos: ElementoDetalle.receta -> químicos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                # Detalle con elementos: ElementoDetalle.kit -> herramientas
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                # Detalle con elementos: ElementoDetalle.consumo
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.consumo),

                # Metodología/pasos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.metodologia)
                    .joinedload(Metodologia.pasos),
            )
            .filter_by(sop_id=sop.sop_id)
            .first()
        )
        if not sop_full:
            continue

        fracciones_filtradas = []

        for sf in sop_full.sop_fracciones or []:
            sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == nivel_id), None)
            if not sd:
                continue

            fr = sf.fraccion
            metodologia = sd.metodologia

            receta = sd.receta
            kit = sd.kit
            elemento_set = sd.elemento_set
            consumo_sd = getattr(sd, "consumo", None)

            tiempo_min = float(sd.tiempo_unitario_min) if sd.tiempo_unitario_min is not None else None

            # ====== ARMADO DE TABLA UNICA POR FRACCIÓN ======
            tabla = None

            if elemento_set:
                headers = ["Elemento", "Cantidad", "Químico", "Receta", "Consumo", "Herramienta"]
                rows = []

                for ed in (elemento_set.detalles or []):
                    elemento = getattr(ed, "elemento", None)

                    q_str, r_str = fmt_quimico_y_receta(getattr(ed, "receta", None))
                    c_str = fmt_consumo(getattr(ed, "consumo", None))
                    h_str = fmt_herramientas(getattr(ed, "kit", None))

                    rows.append([
                        na(getattr(elemento, "nombre", None)),
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
                h_str = fmt_herramientas(kit)

                tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}

            fracciones_filtradas.append({
                "orden": sf.orden,
                "fraccion_nombre": fr.fraccion_nombre if fr else "",
                "descripcion": (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_asignado,
                "tiempo_min": round(tiempo_min, 2) if tiempo_min is not None else None,
                "metodologia": metodologia,

                # ✅ lo nuevo
                "tabla": tabla,

                "observacion_critica": (fr.nota_tecnica if fr else None),
            })

        detalles.append({
            "tarea_id": t.tarea_id,
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "sop_codigo": sop.sop_id,
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas
        })

    detalles.sort(
        key=lambda d: (
            getattr(SubArea.query.filter_by(subarea_nombre=d["subarea"]).first(), "orden_subarea", 9999)
        )
    )

    return render_template("reporte_personal.html", persona=persona, fecha=fecha_obj, detalles=detalles)


# =========================
# REPORTE Persona PDF (macro) — sop_macro_pdf.html
# =========================
@main_bp.route("/reporte/<fecha>/<personal_id>/pdf")
def reporte_persona_dia_pdf(fecha, personal_id):
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
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.fraccion),

                # Detalle sin elementos: kit/herramientas
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                # Detalle sin elementos: receta/químicos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                # Detalle sin elementos: consumo
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.consumo),

                # Detalle con elementos: elemento_set -> elemento
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.elemento),

                # Detalle con elementos: ElementoDetalle.receta -> químicos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),

                # Detalle con elementos: ElementoDetalle.kit -> herramientas
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),

                # Detalle con elementos: ElementoDetalle.consumo
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.consumo),

                # Metodología/pasos
                joinedload(SOP.sop_fracciones)
                    .joinedload(SopFraccion.detalles)
                    .joinedload(SopFraccionDetalle.metodologia)
                    .joinedload(Metodologia.pasos),
            )
            .filter_by(sop_id=sop.sop_id)
            .first()
        )
        if not sop_full:
            continue

        fracciones_filtradas = []

        for sf in sop_full.sop_fracciones or []:
            sd = next((d for d in (sf.detalles or []) if d.nivel_limpieza_id == nivel_id), None)
            if not sd:
                continue

            fr = sf.fraccion
            metodologia = sd.metodologia

            # Metodología a dict (para PDF)
            metodologia_dict = None
            if metodologia:
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

            # ====== TABLA UNICA POR FRACCIÓN ======
            tabla = None

            if elemento_set:
                headers = ["Elemento", "Cantidad", "Químico", "Receta", "Consumo", "Herramienta"]
                rows = []

                for ed in (elemento_set.detalles or []):
                    elemento = getattr(ed, "elemento", None)

                    q_str, r_str = fmt_quimico_y_receta(getattr(ed, "receta", None))
                    c_str = fmt_consumo(getattr(ed, "consumo", None))
                    h_str = fmt_herramientas(getattr(ed, "kit", None))

                    rows.append([
                        na(getattr(elemento, "nombre", None)),
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
                h_str = fmt_herramientas(kit)
                tabla = {"headers": headers, "rows": [[q_str, r_str, c_str, h_str]]}

            fracciones_filtradas.append({
                "orden": sf.orden,
                "fraccion_nombre": fr.fraccion_nombre if fr else "",
                "descripcion": (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_asignado,
                "tiempo_base": round(tiempo_min, 2) if tiempo_min is not None else None,  # macro usa tiempo_base

                # ✅ lo nuevo
                "tabla": tabla,

                "nota_tecnica": (fr.nota_tecnica if fr else None),
                "observacion_critica": sop.observacion_critica_sop,
                "metodologia": metodologia_dict,
            })

        detalles.append({
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "sop_codigo": sop.sop_id,
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas
        })

    detalles.sort(
        key=lambda d: (
            getattr(SubArea.query.filter_by(subarea_nombre=d["subarea"]).first(), "orden_subarea", 9999)
        )
    )

    html = render_template("sop_macro_pdf.html", persona=persona, fecha=fecha_obj, detalles=detalles)
    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=PDF_OPTIONS)

    return make_response((pdf_bytes, 200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename=SOP_{personal_id}_{fecha}.pdf"
    }))


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

def crear_tarea(fecha_obj: date, personal_id, area_id, subarea_id, nivel):
    dia = upsert_dia(fecha_obj)
    t = LanzamientoTarea(
        dia_id=dia.dia_id,
        personal_id=personal_id,
        area_id=area_id,
        subarea_id=subarea_id,
        nivel_limpieza_asignado=canon_nivel(nivel) or "basica"
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
        if not existe_tarea(fecha_dest, it.personal_id, it.subarea_id):
            crear_tarea(fecha_dest, it.personal_id, it.area_id, it.subarea_id, canon_nivel(it.nivel_limpieza_asignado) or "basica")
    db.session.commit()

# =========================
# UI: GET formulario aplicar plantilla
# =========================
@main_bp.route("/plantillas/aplicar")
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
def borrar_plantilla(plantilla_id):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    PlantillaItem.query.filter_by(plantilla_id=plantilla_id).delete()
    db.session.delete(plantilla)
    db.session.commit()
    flash(f'Plantilla "{plantilla.nombre}" eliminada correctamente.', "success")
    return redirect(url_for("main.home"))
