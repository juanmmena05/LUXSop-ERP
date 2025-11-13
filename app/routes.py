import io
import os
import unicodedata
from typing import Optional
from datetime import datetime, date, timedelta

import pdfkit
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, make_response
from sqlalchemy.orm import joinedload

from .models import (
    db,
    Area,
    SubArea,
    SOP,
    Fraccion,
    FraccionDetalle,
    Metodologia,
    NivelLimpieza,
    Personal,
    LanzamientoSemana,
    LanzamientoDia,
    LanzamientoTarea,
    AsignacionPersonal,
    PlantillaSemanal,
    PlantillaItem,
    PlantillaSemanaAplicada,
    Elemento,
    ElementoSet,
    ElementoDetalle,
    Kit,
    KitDetalle,
    Herramienta,
    Receta,
    RecetaDetalle,
    Quimico
)

# =========================
# Helpers de PDF
# =========================
WKHTMLTOPDF_CMD = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_CMD)

PDF_OPTIONS = {
    "page-size": "A5",        # más angosto, cómodo para pantalla de teléfono
    "encoding": "UTF-8",
    "margin-top": "6mm",
    "margin-bottom": "6mm",
    "margin-left": "6mm",
    "margin-right": "6mm",
    "zoom": "1.15",           # texto ~15% más grande
    # "no-outline": None,     # opcional
    # "quiet": ""             # opcional
}

# =========================
# Helpers de semana/día
# =========================
def get_monday(d: date) -> date:
    # Lunes = 0
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

# --- Helper: set etiqueta de plantilla activa para una semana ---
def set_plantilla_activa(lunes_semana: date, plantilla_id: Optional[int]):
    fila = PlantillaSemanaAplicada.query.get(lunes_semana)
    if not fila:
        fila = PlantillaSemanaAplicada(semana_lunes=lunes_semana, plantilla_id=plantilla_id)
        db.session.add(fila)
    else:
        fila.plantilla_id = plantilla_id
        fila.aplicada_en = datetime.utcnow()
    db.session.commit()

def obtener_tarea(fecha_obj: date, personal_id, subarea_id):
    """Devuelve la tarea existente para (fecha, persona, subárea) o None."""
    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return None
    return db.session.query(LanzamientoTarea).filter_by(
        dia_id=dia.dia_id,
        personal_id=personal_id,
        subarea_id=subarea_id
    ).first()

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

main_bp = Blueprint('main', __name__)

# =========================
# HOME (panel semanal)
# =========================
@main_bp.route('/')
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
            "link_ruta": url_for('main.ruta_dia', fecha=fecha_dia.strftime("%Y-%m-%d")),
            "link_plan": url_for('main.plan_dia_asignar', fecha=fecha_dia.strftime("%Y-%m-%d")),
        })

    sabado = lunes + timedelta(days=5)

    # Plantillas disponibles y etiqueta activa
    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    plantilla_activa = PlantillaSemanaAplicada.query.get(lunes)  # puede ser None

    return render_template(
        'home.html',
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
@main_bp.route('/initdb')
def initdb():
    db.create_all()
    return "Base de datos creada (tablas listas)."

# =========================
# ÁREAS
# =========================
@main_bp.route('/areas')
def listar_areas():
    areas = Area.query.all()
    return render_template('areas_list.html', areas=areas)

@main_bp.route('/areas/nueva', methods=['GET', 'POST'])
def nueva_area():
    # OJO: El modelo Area NO tiene superficie_area ni tiempo_total_area.
    if request.method == 'POST':
        area_id = request.form.get('area_id')
        area_nombre = request.form.get('area_nombre')
        tipo_area = request.form.get('tipo_area')
        cantidad_subareas = int(request.form.get('cantidad_subareas') or 0)

        db.session.add(Area(
            area_id=area_id,
            area_nombre=area_nombre,
            tipo_area=tipo_area,
            cantidad_subareas=cantidad_subareas,
        ))
        db.session.commit()
        return redirect(url_for('main.listar_areas'))
    return render_template('areas_form.html')

# =========================
# SUBÁREAS
# =========================
@main_bp.route('/subareas')
def listar_subareas():
    subareas = SubArea.query.all()
    return render_template('subareas_list.html', subareas=subareas)

@main_bp.route('/subareas/nueva', methods=['GET', 'POST'])
def nueva_subarea():
    areas = Area.query.all()
    if request.method == 'POST':
        subarea_id = request.form.get('subarea_id')
        area_id = request.form.get('area_id')
        subarea_nombre = request.form.get('subarea_nombre')
        superficie_subarea = float(request.form.get('superficie_subarea') or 0)
        nivel_limpieza = request.form.get('nivel_limpieza')
        frecuencia = float(request.form.get('frecuencia') or 0)

        db.session.add(SubArea(
            subarea_id=subarea_id,
            area_id=area_id,
            subarea_nombre=subarea_nombre,
            superficie_subarea=superficie_subarea,
            nivel_limpieza=nivel_limpieza,
            frecuencia=frecuencia,
        ))
        db.session.commit()
        return redirect(url_for('main.listar_subareas'))
    return render_template('subareas_form.html', areas=areas)

# =========================
# PERSONAL
# =========================
@main_bp.route('/personal/nuevo', methods=['GET', 'POST'])
def personal_nuevo():
    if request.method == 'POST':
        personal_id = request.form.get('personal_id')
        nombre = request.form.get('nombre')

        db.session.add(Personal(personal_id=personal_id, nombre=nombre))
        db.session.commit()
        return redirect(url_for('main.asignar_ruta', personal_id=personal_id))
    return render_template('personal_form.html')

# =========================
# ASIGNACIÓN RUTA A PERSONAL (catálogo opcional)
# =========================
@main_bp.route('/personal/<personal_id>/asignar', methods=['GET', 'POST'])
def asignar_ruta(personal_id):
    persona = Personal.query.filter_by(personal_id=personal_id).first()
    areas = Area.query.all()
    subareas = SubArea.query.all()

    if request.method == 'POST':
        area_id = request.form.get('area_id')
        subarea_id = request.form.get('subarea_id')
        nivel_limpieza_asignado = canon_nivel(request.form.get('nivel_limpieza_asignado'))
        if not nivel_limpieza_asignado:
            flash('Nivel de limpieza inválido.', 'warning')
            return redirect(url_for('main.asignar_ruta', personal_id=personal_id))

        db.session.add(AsignacionPersonal(
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado,
        ))
        db.session.commit()
        return redirect(url_for('main.asignar_ruta', personal_id=personal_id))

    asignaciones = AsignacionPersonal.query.filter_by(personal_id=personal_id).all()
    return render_template(
        'asignacion_form.html',
        persona=persona, areas=areas, subareas=subareas, asignaciones=asignaciones
    )

# =========================
# BORRAR ASIGNACIÓN (día)
# =========================
@main_bp.route('/plan/<fecha>/borrar/<int:tarea_id>', methods=['POST'])
def borrar_tarea(fecha, tarea_id):
    tarea = LanzamientoTarea.query.get_or_404(tarea_id)
    db.session.delete(tarea)
    db.session.commit()
    return redirect(url_for('main.plan_dia_asignar', fecha=fecha))

# =========================
# AJAX: subáreas por área
# =========================
@main_bp.route('/subareas_por_area/<area_id>')
def subareas_por_area(area_id):
    # Trae la fecha para saber qué subáreas están ocupadas ese día
    fecha_str = request.args.get('fecha')
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

    subareas = SubArea.query.filter_by(area_id=area_id).all()
    return jsonify([
        {"id": s.subarea_id, "nombre": s.subarea_nombre, "ocupada": s.subarea_id in ocupadas}
        for s in subareas
    ])

# =========================
# PLAN DIARIO (asignar)
# =========================
@main_bp.route('/plan/<fecha>/asignar', methods=['GET', 'POST'])
def plan_dia_asignar(fecha):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    dia = get_or_create_dia(fecha_obj)

    personal_list = Personal.query.all()
    areas_list = Area.query.all()

    # Subáreas ya asignadas ese día (para pintar en el select)
    asignadas_ids = [
        s[0] for s in db.session.query(LanzamientoTarea.subarea_id)
        .filter(LanzamientoTarea.dia_id == dia.dia_id)
        .distinct()
        .all()
    ]

    # Mostrar TODAS las subáreas (las ya asignadas se desactivan en el template)
    subareas_list = SubArea.query.all()

    if request.method == 'POST':
        personal_id = request.form.get('personal_id')
        area_id = request.form.get('area_id')
        subarea_id = request.form.get('subarea_id')
        nivel_limpieza_asignado = canon_nivel(request.form.get('nivel_limpieza_asignado'))
        if not nivel_limpieza_asignado:
            flash('Nivel de limpieza inválido.', 'warning')
            return redirect(url_for('main.plan_dia_asignar', fecha=fecha))

        # BLOQUEO EN SERVIDOR: misma subárea ya usada ese día
        existe_misma_subarea = db.session.query(LanzamientoTarea).filter_by(
            dia_id=dia.dia_id,
            subarea_id=subarea_id
        ).first()

        if existe_misma_subarea:
            flash('Esa subárea ya tiene una tarea asignada en este día.', 'warning')
            return redirect(url_for('main.plan_dia_asignar', fecha=fecha))

        # Crear la tarea
        db.session.add(LanzamientoTarea(
            dia_id=dia.dia_id,
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado
        ))
        db.session.commit()
        return redirect(url_for('main.plan_dia_asignar', fecha=fecha))

    # GET: tareas del día
    tareas_del_dia = (
        db.session.query(LanzamientoTarea)
        .filter(LanzamientoTarea.dia_id == dia.dia_id)
        .all()
    )

    # tiempos
    tiempos_por_tarea = {t.tarea_id: calcular_tiempo_tarea(t) for t in tareas_del_dia}

    # agrupar por persona
    tareas_por_persona = {}
    for t in tareas_del_dia:
        key = t.personal_id
        if key not in tareas_por_persona:
            persona = getattr(t, "personal", None) or Personal.query.filter_by(personal_id=key).first()
            tareas_por_persona[key] = {"persona": persona, "subtareas": []}
        tareas_por_persona[key]["subtareas"].append(t)

    # IDs de subáreas asignadas ese día (set para el template)
    asignadas_ids = {t.subarea_id for t in tareas_del_dia}

    return render_template(
        'plan_dia_form.html',
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
# REPORTE (fecha + persona)
# =========================
@main_bp.route('/reporte/<fecha>/<personal_id>')
def reporte_persona_dia(fecha, personal_id):
    """
    Genera el reporte SOP Diario para una persona en una fecha específica.
    Incluye metodología, kit, receta, elemento_set y todos los detalles.
    """
    # Convertir fecha a objeto
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()

    # Buscar el día de lanzamiento
    dia = LanzamientoDia.query.filter_by(fecha=fecha_obj).first()
    if not dia:
        return f"No existe un registro de día para la fecha {fecha}.", 404

    # Tareas de esa persona en ese día
    tareas = LanzamientoTarea.query.filter_by(dia_id=dia.dia_id, personal_id=personal_id).all()
    if not tareas:
        persona = Personal.query.filter_by(personal_id=personal_id).first()
        nombre = persona.nombre if persona else personal_id
        return f"No hay tareas para {nombre} el {fecha}.", 404

    persona = tareas[0].personal if tareas else None
    detalles = []

    # Recorremos las tareas asignadas al colaborador
    for t in tareas:
        area = t.area
        subarea = t.subarea
        if not area or not subarea:
            continue

        sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first()
        if not sop:
            continue

        # Canon + id
        nivel_asignado = canon_nivel(t.nivel_limpieza_asignado)
        nivel_id = nivel_to_id(nivel_asignado)
        if not nivel_id:
            continue

        # Factor del nivel
        nivel_obj = NivelLimpieza.query.get(nivel_id)
        factor_nivel = float(getattr(nivel_obj, "factor_nivel", 1.0) or 1.0)

        # Superficie (solo se usará en por_m2)
        superficie_m2 = float(getattr(subarea, "superficie_subarea", 0) or 0)
        if superficie_m2 <= 0:
            superficie_m2 = 1.0

        # Precarga de relaciones para eficiencia
        fracciones = (
            db.session.query(Fraccion)
            .options(
                joinedload(Fraccion.detalles)
                .joinedload(FraccionDetalle.kit)
                .joinedload(Kit.detalles)
                .joinedload(KitDetalle.herramienta),
                joinedload(Fraccion.detalles)
                .joinedload(FraccionDetalle.receta)
                .joinedload(Receta.detalles)
                .joinedload(RecetaDetalle.quimico),
                joinedload(Fraccion.detalles)
                .joinedload(FraccionDetalle.elemento_set)
                .joinedload(ElementoSet.detalles)
                .joinedload(ElementoDetalle.elemento),
            )
            .filter_by(sop_id=sop.sop_id)
            .order_by(Fraccion.orden)
            .all()
        )

        fracciones_filtradas = []

        # Procesamos cada fracción (tarea pequeña)
        for f in fracciones:
            fd = next((d for d in f.detalles if d.nivel_limpieza_id == nivel_id), None)
            if not fd:
                continue

            metodologia = Metodologia.query.filter_by(metodologia_id=fd.metodologia_id).first()

            # --- Relaciones ---
            receta = getattr(fd, "receta", None)
            kit = getattr(fd, "kit", None)
            elemento_set = getattr(fd, "elemento_set", None)

            if not receta and fd.receta_id:
                receta = Receta.query.filter_by(receta_id=fd.receta_id).first()
            if not kit and fd.kit_id:
                kit = Kit.query.filter_by(kit_id=fd.kit_id).first()
            if not elemento_set and fd.elemento_set_id:
                elemento_set = ElementoSet.query.filter_by(elemento_set_id=fd.elemento_set_id).first()

            # ===== Tiempo calculado POR FRACCIÓN =====
            tiempo_base = float(getattr(f, "tiempo_base_min", 0) or 0)
            tipo_formula = (getattr(f, "tipo_formula", "") or "").lower()
            ajuste = float(getattr(fd, "ajuste_factor", 1.0) or 1.0)

            # multiplicador según tipo de fórmula (RESPETA superficie_aplicable)
            if tipo_formula in ("por_m2", "por_m²"):
                if fd and fd.superficie_aplicable not in (None, 0, "", " "):
                    try:
                        multiplicador = float(fd.superficie_aplicable)
                        if multiplicador <= 0:
                            multiplicador = superficie_m2
                    except (TypeError, ValueError):
                        multiplicador = superficie_m2
                else:
                    multiplicador = superficie_m2

            elif tipo_formula == "por_pieza":
                elemento_set = getattr(fd, "elemento_set", None)
                if elemento_set and getattr(elemento_set, "detalles", None):
                    multiplicador = max(1, len(elemento_set.detalles))
                else:
                    multiplicador = 1.0
            else:  # fijo u otro
                multiplicador = 1.0

            tiempo_calculado = calcular_tiempo_fraccion(
                f=f,
                fd=fd,
                superficie_m2=superficie_m2,
                factor_nivel=factor_nivel,
            )

            # ===== Texto de productos/herramientas y tabla de elementos =====
            producto_txt = ""
            herramienta_txt = ""
            elementos_tabla = []

            if elemento_set:
                elementos_detalle = ElementoDetalle.query.filter_by(elemento_set_id=elemento_set.elemento_set_id).all()
                for ed in elementos_detalle:
                    elemento = getattr(ed, "elemento", None)
                    if not elemento and ed.elemento_id:
                        elemento = Elemento.query.filter_by(elemento_id=ed.elemento_id).first()

                    receta_ed = getattr(ed, "receta", None)
                    kit_ed = getattr(ed, "kit", None)

                    if not receta_ed and ed.receta_id:
                        receta_ed = Receta.query.filter_by(receta_id=ed.receta_id).first()
                    if not kit_ed and ed.kit_id:
                        kit_ed = Kit.query.filter_by(kit_id=ed.kit_id).first()

                    producto_str = ""
                    if receta_ed:
                        if getattr(receta_ed, "detalles", None):
                            productos = [f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})" for d in receta_ed.detalles]
                            producto_str = " + ".join(productos)
                        else:
                            producto_str = receta_ed.nombre

                    herramienta_str = ""
                    if kit_ed:
                        herramientas = [kd.herramienta.nombre for kd in kit_ed.detalles]
                        herramienta_str = " - ".join(herramientas) if herramientas else kit_ed.nombre

                    elementos_tabla.append({
                        "nombre": elemento.nombre if elemento else "",
                        "material": getattr(elemento, "material", "") if elemento else "",
                        "cantidad": getattr(elemento, "cantidad", "") if elemento else "",
                        "producto": producto_str,
                        "herramienta": herramienta_str
                    })
            else:
                if receta:
                    if getattr(receta, "detalles", None):
                        productos = [f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})" for d in receta.detalles]
                        producto_txt = " + ".join(productos)
                    else:
                        producto_txt = receta.nombre
                if kit:
                    herramientas = [det.herramienta.nombre for det in kit.detalles]
                    herramienta_txt = " | ".join(herramientas) if herramientas else kit.nombre

            if not producto_txt and receta:
                producto_txt = receta.nombre
            if not herramienta_txt and kit:
                herramienta_txt = kit.nombre

            # Armamos la fracción
            fracciones_filtradas.append({
                "orden": f.orden,
                "fraccion_nombre": f.fraccion_nombre,
                "descripcion": f.descripcion or (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_asignado,
                "tiempo_min": round(tiempo_calculado, 2),
                "base": tiempo_base,
                "ajuste": ajuste,
                "factor_nivel": factor_nivel,
                "metodologia": metodologia,
                "producto": producto_txt or None,
                "herramienta": herramienta_txt or None,
                "elementos_tabla": elementos_tabla or None,
                "observacion_critica": getattr(f, "nota_tecnica", None)
            })

        # Bloque de detalles generales
        detalles.append({
            "tarea_id": t.tarea_id,
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "sop_codigo": sop.sop_codigo,
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas
        })

    # Ordenar por el orden_subarea definido en la BD
    detalles.sort(
        key=lambda d: (
            getattr(
                SubArea.query.filter_by(subarea_nombre=d["subarea"]).first(),
                "orden_subarea",
                9999
            )
        )
    )

    # Render final
    return render_template("reporte_personal.html", persona=persona, fecha=fecha_obj, detalles=detalles)

# =========================
# REPORTE Persona PDF
# =========================
@main_bp.route('/reporte/<fecha>/<personal_id>/pdf')
def reporte_persona_dia_pdf(fecha, personal_id):
    """
    PDF MACRO — SOP completo de la persona (todas las subáreas y fracciones filtradas por nivel),
    incluyendo metodología y pasos (metodología cuelga de FraccionDetalle).
    """
    # 1) Validar fecha y existencia de día/tareas
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

    # 3) Recorrer tareas
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

        # factor nivel + superficie m2
        nivel_obj = NivelLimpieza.query.get(nivel_id)
        factor_nivel = float(getattr(nivel_obj, "factor_nivel", 1.0) or 1.0)

        superficie_m2 = float(getattr(subarea, "superficie_subarea", 0) or 0)
        if superficie_m2 <= 0:
            superficie_m2 = 1.0

        # 4) Precargar fracciones con TODO lo necesario (kits, recetas, elementos y METODOLOGÍA + PASOS)
        fracciones = (
            db.session.query(Fraccion)
            .options(
                joinedload(Fraccion.detalles)
                    .joinedload(FraccionDetalle.kit)
                    .joinedload(Kit.detalles)
                    .joinedload(KitDetalle.herramienta),
                joinedload(Fraccion.detalles)
                    .joinedload(FraccionDetalle.receta)
                    .joinedload(Receta.detalles)
                    .joinedload(RecetaDetalle.quimico),
                joinedload(Fraccion.detalles)
                    .joinedload(FraccionDetalle.elemento_set)
                    .joinedload(ElementoSet.detalles)
                    .joinedload(ElementoDetalle.elemento),
                joinedload(Fraccion.detalles)
                    .joinedload(FraccionDetalle.metodologia)
                    .joinedload(Metodologia.pasos),
            )
            .filter_by(sop_id=sop.sop_id)
            .order_by(Fraccion.orden)
            .all()
        )

        fracciones_filtradas = []

        for f in fracciones:
            # Seleccionar el detalle que corresponde al nivel asignado
            fd = next((d for d in f.detalles if d.nivel_limpieza_id == nivel_id), None)
            if not fd:
                continue

            # --- Metodología desde FraccionDetalle
            metodologia = getattr(fd, "metodologia", None)
            metodologia_dict = None
            if metodologia:
                pasos_items = sorted(list(metodologia.pasos or []), key=lambda p: (p.orden or 0))
                pasos = [{"instruccion": p.instruccion} for p in pasos_items]
                metodologia_dict = {
                    "descripcion": metodologia.descripcion or "",
                    "pasos": pasos
                }

            # ===== Tiempo calculado POR FRACCIÓN =====
            tiempo_base = float(getattr(f, "tiempo_base_min", 0) or 0)
            tipo_formula = (getattr(f, "tipo_formula", "") or "").lower()
            ajuste = float(getattr(fd, "ajuste_factor", 1.0) or 1.0)

            if tipo_formula in ("por_m2", "por_m²"):
                if fd and fd.superficie_aplicable not in (None, 0, "", " "):
                    try:
                        multiplicador = float(fd.superficie_aplicable)
                        if multiplicador <= 0:
                            multiplicador = superficie_m2
                    except (TypeError, ValueError):
                        multiplicador = superficie_m2
                else:
                    multiplicador = superficie_m2

            elif tipo_formula == "por_pieza":
                elemento_set = getattr(fd, "elemento_set", None)
                if elemento_set and getattr(elemento_set, "detalles", None):
                    multiplicador = max(1, len(elemento_set.detalles))
                else:
                    multiplicador = 1.0
            else:  # fijo u otro
                multiplicador = 1.0

            tiempo_calculado = calcular_tiempo_fraccion(
                f=f,
                fd=fd,
                superficie_m2=superficie_m2,
                factor_nivel=factor_nivel,
            )

            # --- Receta / Kit / ElementoSet (para tabla)
            receta = getattr(fd, "receta", None)
            kit = getattr(fd, "kit", None)
            elemento_set = getattr(fd, "elemento_set", None)

            producto_txt = ""
            herramienta_txt = ""
            elementos_tabla = []

            if elemento_set:
                elementos_detalle = ElementoDetalle.query.filter_by(elemento_set_id=elemento_set.elemento_set_id).all()
                for ed in elementos_detalle:
                    elemento = getattr(ed, "elemento", None)
                    if not elemento and ed.elemento_id:
                        elemento = Elemento.query.filter_by(elemento_id=ed.elemento_id).first()

                    receta_ed = getattr(ed, "receta", None)
                    kit_ed = getattr(ed, "kit", None)

                    if not receta_ed and ed.receta_id:
                        receta_ed = Receta.query.filter_by(receta_id=ed.receta_id).first()
                    if not kit_ed and ed.kit_id:
                        kit_ed = Kit.query.filter_by(kit_id=ed.kit_id).first()

                    producto_str = ""
                    if receta_ed:
                        if getattr(receta_ed, "detalles", None):
                            productos = [f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})" for d in receta_ed.detalles]
                            producto_str = " + ".join(productos)
                        else:
                            producto_str = receta_ed.nombre

                    herramienta_str = ""
                    if kit_ed:
                        herramientas = [kd.herramienta.nombre for kd in kit_ed.detalles]
                        herramienta_str = " - ".join(herramientas) if herramientas else kit_ed.nombre

                    elementos_tabla.append({
                        "nombre": elemento.nombre if elemento else "",
                        "material": getattr(elemento, "material", "") if elemento else "",
                        "cantidad": getattr(elemento, "cantidad", "") if elemento else "",
                        "producto": producto_str,
                        "herramienta": herramienta_str
                    })
            else:
                if receta:
                    if getattr(receta, "detalles", None):
                        productos = [f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})" for d in receta.detalles]
                        producto_txt = " + ".join(productos)
                    else:
                        producto_txt = receta.nombre
                if kit:
                    herramientas = [det.herramienta.nombre for det in kit.detalles]
                    herramienta_txt = " - ".join(herramientas) if herramientas else kit.nombre

            # --- Armar fracción para el template PDF
            fracciones_filtradas.append({
                "orden": f.orden,
                "fraccion_nombre": f.fraccion_nombre,
                "descripcion": f.descripcion or (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_asignado,   # canon
                "tiempo_base": round(tiempo_calculado, 2),
                "producto": producto_txt or None,
                "herramienta": herramienta_txt or None,
                "elementos_tabla": elementos_tabla or None,
                "nota_tecnica": getattr(f, "nota_tecnica", None),
                "observacion_critica": sop.observacion_critica_sop,
                "metodologia": metodologia_dict,
            })

        detalles.append({
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,  # canon
            "sop_codigo": sop.sop_codigo,
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas
        })

    # 5) Orden final por área/subárea
    detalles.sort(
        key=lambda d: (
            getattr(
                SubArea.query.filter_by(subarea_nombre=d["subarea"]).first(),
                "orden_subarea",
                9999
            )
        )
    )

    # 6) Render del HTML y generación del PDF
    html = render_template("sop_macro_pdf.html", persona=persona, fecha=fecha_obj, detalles=detalles)
    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=PDF_OPTIONS)

    return make_response((pdf_bytes, 200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename=SOP_{personal_id}_{fecha}.pdf"
    }))

# =========================
# Calcular Tiempo Tarea
# =========================
def calcular_tiempo_tarea(tarea, modo="total"):
    """
    Calcula el tiempo total o por fracción para una tarea específica.

    Parámetros:
        - tarea: instancia de LanzamientoTarea
        - modo: "total" → float (tiempo total), "detalles" → list[dict]

    Retorna:
        - float si modo="total"
        - list[dict] si modo="detalles"
    """
    # --- Subárea y superficie base ---
    subarea = getattr(tarea, "subarea", None) or SubArea.query.get(tarea.subarea_id)
    superficie = float(getattr(subarea, "superficie_subarea", 0) or 0)
    if superficie <= 0:
        superficie = 1.0

    # --- Nivel de limpieza y su factor ---
    nivel_text = canon_nivel(tarea.nivel_limpieza_asignado)
    nivel_id = nivel_to_id(nivel_text) or 1
    nivel_obj = NivelLimpieza.query.get(nivel_id)
    factor_nivel = float(getattr(nivel_obj, "factor_nivel", 1.0) or 1.0)

    # --- SOP y fracciones ---
    sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first() if subarea else None
    if not sop:
        return 0.0 if modo == "total" else []

    fracciones = (
        Fraccion.query
        .filter_by(sop_id=sop.sop_id)
        .order_by(Fraccion.orden)
        .all()
    )

    total_min = 0.0
    detalles = []

    for f in fracciones:
        # FraccionDetalle según nivel de limpieza
        fd = None
        if nivel_obj:
            fd = FraccionDetalle.query.filter_by(
                fraccion_id=f.fraccion_id,
                nivel_limpieza_id=nivel_obj.nivel_limpieza_id
            ).first()

        tiempo_fraccion_total = calcular_tiempo_fraccion(
            f=f,
            fd=fd,
            superficie_m2=superficie,
            factor_nivel=factor_nivel,
        )
        total_min += tiempo_fraccion_total

        if modo == "detalles":
            tipo_formula = (f.tipo_formula or "").strip().lower()
            ajuste = float(getattr(fd, "ajuste_factor", 1.0) if fd else 1.0)
            es_manual = bool(fd and fd.tiempo_unitario_min is not None)

            detalles.append({
                "fraccion_id": f.fraccion_id,
                "nombre": f.fraccion_nombre or "",
                "tipo_formula": tipo_formula,
                "es_tiempo_manual": es_manual,

                # Qué base se usó realmente:
                # - si es manual: el tiempo total medido
                # - si no es manual: el tiempo_base_min de la fracción
                "base_usada": (
                    float(fd.tiempo_unitario_min)
                    if es_manual
                    else float(getattr(f, "tiempo_base_min", 0) or 0)
                ),

                # Por si quieres mostrarlo en la UI
                "tiempo_manual": float(fd.tiempo_unitario_min) if es_manual else None,

                # Solo tienen sentido cuando NO es manual
                "ajuste": ajuste if not es_manual else 1.0,
                "factor_nivel": factor_nivel if not es_manual else 1.0,

                # Resultado final que sale del helper (ya redondeado)
                "tiempo_fraccion": round(tiempo_fraccion_total, 2),
            })

    return round(total_min, 2) if modo == "total" else detalles




# =========================
# Calcular Tiempo Fraccion 
# =========================
def calcular_tiempo_fraccion(f: Fraccion,
                             fd: Optional[FraccionDetalle],
                             superficie_m2: float,
                             factor_nivel: float) -> float:
    """
    Calcula los minutos para UNA fracción.

    Reglas:
      1) Si fd.tiempo_unitario_min NO es None → se devuelve TAL CUAL (override total).
      2) Si es None → se usa la fórmula:
            tiempo = tiempo_base_min * superficie_app * ajuste * factor_nivel
    """
    # 1) Override total: tiempo medido en campo
    if fd and fd.tiempo_unitario_min is not None:
        try:
            return float(fd.tiempo_unitario_min)
        except (TypeError, ValueError):
            # Si viene algo raro, caemos a la fórmula normal
            pass

    # 2) Fórmula normal
    tipo_formula = (getattr(f, "tipo_formula", "") or "").strip().lower()

    # --- multiplicador (superficie_app) ---
    if tipo_formula in ("por_m2", "por_m²"):
        if fd and fd.superficie_aplicable not in (None, 0, "", " "):
            try:
                superficie_app = float(fd.superficie_aplicable)
                if superficie_app <= 0:
                    superficie_app = superficie_m2
            except (TypeError, ValueError):
                superficie_app = superficie_m2
        else:
            superficie_app = superficie_m2

    elif tipo_formula == "por_pieza":
        if fd and getattr(fd, "elemento_set", None) and getattr(fd.elemento_set, "detalles", None):
            superficie_app = max(1, len(fd.elemento_set.detalles))
        else:
            superficie_app = 1.0
    else:
        superficie_app = 1.0

    ajuste = float(getattr(fd, "ajuste_factor", 1.0) or 1.0)
    tiempo_base = float(getattr(f, "tiempo_base_min", 0) or 0)

    total = tiempo_base * superficie_app * ajuste * factor_nivel
    return total


# =========================
# Ruta Dia
# =========================
@main_bp.route('/plan/<fecha>/ruta')
def ruta_dia(fecha):
    """
    Centro de reportes del día: lista de personas con tareas ese día
    y link directo a su SOP diario.
    """
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

    return render_template('ruta_dia.html', fecha=fecha_obj, personas=personas)

# ====== HELPERS DE PLANTILLA ======
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
    return db.session.query(LanzamientoTarea).filter_by(
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
        fecha_dest  = destino_lunes + timedelta(days=i)
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

# ====== UI: GET formulario de aplicación de plantilla ======
@main_bp.route('/plantillas/aplicar')
def plantillas_aplicar_form():
    hoy = date.today()
    lunes_destino = get_monday(hoy)
    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    lunes_anterior = lunes_destino - timedelta(days=7)
    return render_template('plantillas_aplicar.html',
                           lunes_destino=lunes_destino,
                           lunes_anterior=lunes_anterior,
                           plantillas=plantillas)

# ====== POST aplicar plantilla ======
@main_bp.route('/plantillas/aplicar', methods=['POST'])
def plantillas_aplicar_post():
    modo = request.form.get('modo')  # 'ruta_base' | 'semana' | 'plantilla'
    overwrite = request.form.get('overwrite') == 'on'
    lunes_destino_str = request.form.get('lunes_destino')  # 'YYYY-MM-DD'
    lunes_destino = datetime.strptime(lunes_destino_str, '%Y-%m-%d').date()

    if modo == 'ruta_base':
        aplicar_ruta_base_personal(lunes_destino, overwrite)

    elif modo == 'semana':
        lunes_origen_str = request.form.get('lunes_origen')
        lunes_origen = datetime.strptime(lunes_origen_str, '%Y-%m-%d').date()
        aplicar_desde_semana(lunes_origen, lunes_destino, overwrite)

    elif modo == 'plantilla':
        plantilla_id = int(request.form.get('plantilla_id'))
        aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite)

    return redirect(url_for('main.home'))

# ====== CRUD mínimo: crear plantilla desde semana actual ======
@main_bp.route('/plantillas/guardar', methods=['POST'])
def guardar_semana_como_plantilla():
    nombre = request.form.get('nombre')  # nombre de la plantilla
    lunes_ref = datetime.strptime(request.form.get('lunes_ref'), '%Y-%m-%d').date()

    if not nombre:
        return "Nombre requerido", 400

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        return "Ya existe una plantilla con ese nombre.", 400

    plantilla = PlantillaSemanal(nombre=nombre)
    db.session.add(plantilla)
    db.session.commit()

    # Tomamos la semana referencia y volcamos a la plantilla
    for i in range(6):
        fecha = lunes_ref + timedelta(days=i)
        dia = LanzamientoDia.query.filter_by(fecha=fecha).first()
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
    return redirect(url_for('main.plantillas_aplicar_form'))

# GUARDAR semana visible como plantilla (nombre + semana)
@main_bp.route('/plantillas/guardar_simple', methods=['POST'])
def guardar_semana_como_plantilla_simple():
    lunes_ref_str = request.form.get('lunes_ref')
    if not lunes_ref_str:
        return "Falta lunes_ref", 400
    lunes_ref = datetime.strptime(lunes_ref_str, '%Y-%m-%d').date()

    overwrite_flag = request.form.get('overwrite_template') == 'on'
    plantilla_id_str = request.form.get('plantilla_id_to_overwrite')  # puede venir vacío
    nombre = request.form.get('nombre')  # usado SOLO cuando no sobrescribimos

    # Caso A: sobrescribir plantilla existente
    if overwrite_flag:
        if not plantilla_id_str:
            flash('Selecciona la plantilla a sobrescribir.', 'warning')
            return redirect(url_for('main.home'))

        plantilla_id = int(plantilla_id_str)
        plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

        # 1) borrar items actuales de esa plantilla
        PlantillaItem.query.filter_by(plantilla_id=plantilla.plantilla_id).delete()

        # 2) volcar nuevamente desde la semana visible
        for i in range(6):
            fecha = lunes_ref + timedelta(days=i)
            dia = LanzamientoDia.query.filter_by(fecha=fecha).first()
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
        flash(f'Plantilla "{plantilla.nombre}" sobrescrita con la semana actual.', 'success')
        return redirect(url_for('main.home'))

    # Caso B: crear NUEVA plantilla
    if not nombre:
        flash('Escribe un nombre para la nueva plantilla.', 'warning')
        return redirect(url_for('main.home'))

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        flash('Ya existe una plantilla con ese nombre.', 'warning')
        return redirect(url_for('main.home'))

    plantilla = PlantillaSemanal(nombre=nombre)
    db.session.add(plantilla)
    db.session.commit()

    for i in range(6):
        fecha = lunes_ref + timedelta(days=i)
        dia = LanzamientoDia.query.filter_by(fecha=fecha).first()
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
    flash(f'Plantilla "{plantilla.nombre}" creada correctamente.', 'success')
    return redirect(url_for('main.home'))

# APLICAR plantilla guardada (o seleccionar "Ninguna" para sólo quitar etiqueta)
@main_bp.route('/plantillas/aplicar_simple', methods=['POST'])
def aplicar_plantilla_guardada_simple():
    lunes_destino_str = request.form.get('lunes_destino')
    plantilla_id_str  = request.form.get('plantilla_id')  # 'none' | id

    if not lunes_destino_str or plantilla_id_str is None:
        return "Faltan datos", 400

    lunes_destino = datetime.strptime(lunes_destino_str, '%Y-%m-%d').date()

    # 1) Si eligen "Ninguna": vaciar semana completa y quitar etiqueta
    if plantilla_id_str == 'none':
        borrar_asignaciones_semana(lunes_destino)     # borra Lun–Sáb
        set_plantilla_activa(lunes_destino, None)     # etiqueta = Ninguna
        flash('Semana vaciada. Plantilla activa: Ninguna.', 'success')
        return redirect(url_for('main.home'))

    # 2) Si eligen una plantilla: reemplazo total
    plantilla_id = int(plantilla_id_str)

    # borrar Lun–Sáb de destino ANTES de aplicar
    borrar_asignaciones_semana(lunes_destino)

    # aplica plantilla — no hace falta overwrite porque ya está limpia
    aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite=False)

    # etiqueta de la semana
    set_plantilla_activa(lunes_destino, plantilla_id)

    flash('Plantilla aplicada. La semana fue reemplazada por completo.', 'success')
    return redirect(url_for('main.home'))

@main_bp.route('/plantillas/borrar/<int:plantilla_id>', methods=['POST'])
def borrar_plantilla(plantilla_id):
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    # Borra los items primero
    PlantillaItem.query.filter_by(plantilla_id=plantilla_id).delete()
    db.session.delete(plantilla)
    db.session.commit()
    from flask import flash
    flash(f'Plantilla "{plantilla.nombre}" eliminada correctamente.', 'success')
    return redirect(url_for('main.home'))
