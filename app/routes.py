import io
import pdfkit
import os
from sqlalchemy.orm import joinedload
from datetime import datetime, date, timedelta
from typing import Optional
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, make_response
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

    # 👇 Nuevo: plantillas disponibles y etiqueta activa
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
    if request.method == 'POST':
        area_id = request.form.get('area_id')
        area_nombre = request.form.get('area_nombre')
        superficie_area = float(request.form.get('superficie_area') or 0)
        tipo_area = request.form.get('tipo_area')
        cantidad_subareas = int(request.form.get('cantidad_subareas') or 0)
        tiempo_total_area = float(request.form.get('tiempo_total_area') or 0)

        db.session.add(Area(
            area_id=area_id,
            area_nombre=area_nombre,
            superficie_area=superficie_area,
            tipo_area=tipo_area,
            cantidad_subareas=cantidad_subareas,
            tiempo_total_area=tiempo_total_area,
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
        tiempo_total_subarea = float(request.form.get('tiempo_total_subarea') or 0)

        db.session.add(SubArea(
            subarea_id=subarea_id,
            area_id=area_id,
            subarea_nombre=subarea_nombre,
            superficie_subarea=superficie_subarea,
            nivel_limpieza=nivel_limpieza,
            frecuencia=frecuencia,
            tiempo_total_subarea=tiempo_total_subarea,
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
        nivel_limpieza_asignado = request.form.get('nivel_limpieza_asignado')

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
    subareas = SubArea.query.filter_by(area_id=area_id).all()
    return jsonify([{"id": s.subarea_id, "nombre": s.subarea_nombre} for s in subareas])

# =========================
# PLAN DIARIO (asignar)
# =========================
@main_bp.route('/plan/<fecha>/asignar', methods=['GET', 'POST'])
def plan_dia_asignar(fecha):
    fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    dia = get_or_create_dia(fecha_obj)

    personal_list = Personal.query.all()
    areas_list = Area.query.all()
    subareas_list = SubArea.query.all()

    if request.method == 'POST':
        personal_id = request.form.get('personal_id')
        area_id = request.form.get('area_id')
        subarea_id = request.form.get('subarea_id')
        nivel_limpieza_asignado = request.form.get('nivel_limpieza_asignado')

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
        .filter(LanzamientoTarea.dia_id == dia.dia_id)   # <-- corregido (antes: dia_actual)
        .all()
    )

    # Calcular tiempo estimado por tarea (dict: tarea_id -> minutos)
    tiempos_por_tarea = {}
    for t in tareas_del_dia:
        tiempos_por_tarea[t.tarea_id] = calcular_tiempo_tarea(t)


    # Agrupar por persona (key = personal_id)
    tareas_por_persona = {}
    for t in tareas_del_dia:
        key = t.personal_id
        if key not in tareas_por_persona:
            # intentar usar relación; si no existe, buscar persona
            persona = getattr(t, "personal", None)
            if persona is None:
                persona = Personal.query.filter_by(personal_id=key).first()
            tareas_por_persona[key] = {"persona": persona, "subtareas": []}
        tareas_por_persona[key]["subtareas"].append(t)

    return render_template(
        'plan_dia_form.html',
        fecha=fecha_obj,
        personal_list=personal_list,
        areas_list=areas_list,
        subareas_list=subareas_list,
        tareas_del_dia=tareas_del_dia,
        tareas_por_persona=tareas_por_persona,
        tiempos_por_tarea=tiempos_por_tarea
    )


# =========================
# REPORTE (fecha + persona) — versión extendida con ElementoSet
# =========================
@main_bp.route('/reporte/<fecha>/<personal_id>')
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

    persona = tareas[0].personal if tareas else None
    detalles = []
    nivel_map = {"basica": 1, "media": 2, "profunda": 3}

    for t in tareas:
        area = t.area
        subarea = t.subarea
        if not area or not subarea:
            continue

        sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first()
        if not sop:
            continue

        nivel_asignado = (t.nivel_limpieza_asignado or "").strip().lower()
        nivel_id = nivel_map.get(nivel_asignado)
        if not nivel_id:
            continue

        fracciones = Fraccion.query.filter_by(sop_id=sop.sop_id).order_by(Fraccion.orden).all()
        fracciones_filtradas = []

        for f in fracciones:
            fd = FraccionDetalle.query.filter_by(fraccion_id=f.fraccion_id, nivel_limpieza_id=nivel_id).first()
            if not fd:
                continue

            metodologia = Metodologia.query.get(fd.metodologia_id)
            receta = fd.receta
            kit = fd.kit

            producto_txt = ""
            herramienta_txt = ""
            elementos_tabla = []

            # 🧩 Si la fracción usa ElementoSet → mostrar detalle por elemento
            if fd.elemento_set_id:
                elementos_detalle = (
                    db.session.query(ElementoDetalle)
                    .filter_by(elemento_set_id=fd.elemento_set_id)
                    .all()
                )
                for ed in elementos_detalle:
                    elemento = ed.elemento
                    receta_ed = ed.receta
                    kit_ed = ed.kit

                    # Producto / Químico (desde receta)
                    producto_str = ""
                    if receta_ed:
                        if receta_ed.detalles:
                            productos = [
                                f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})"
                                for d in receta_ed.detalles
                            ]
                            producto_str = " + ".join(productos)
                        else:
                            producto_str = receta_ed.nombre

                    # Herramienta / Material (desde kit)
                    herramienta_str = ""
                    if kit_ed:
                        herramientas = [kd.herramienta.nombre for kd in kit_ed.detalles]
                        herramienta_str = " - ".join(herramientas) if herramientas else kit_ed.nombre

                    elementos_tabla.append({
                        "nombre": elemento.nombre if elemento else "",
                        "material": elemento.material if elemento else "",
                        "cantidad": elemento.cantidad if elemento else "",
                        "producto": producto_str,
                        "herramienta": herramienta_str
                    })

            # 🧴 Si no hay ElementoSet → usar receta y kit directos
            else:
                if receta:
                    if receta.detalles:
                        productos = [
                            f"{d.quimico.nombre} ({d.dosis}{d.unidad_dosis})"
                            for d in receta.detalles
                        ]
                        producto_txt = " + ".join(productos)
                    else:
                        producto_txt = receta.nombre

                if kit:
                    herramientas = [det.herramienta.nombre for det in kit.detalles]
                    herramienta_txt = " - ".join(herramientas)

            # Fracción final
            fracciones_filtradas.append({
                "orden": f.orden,
                "fraccion_nombre": f.fraccion_nombre,
                "descripcion": f.descripcion or (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": t.nivel_limpieza_asignado,
                "tiempo_base": f.tiempo_base_min,
                "metodologia": metodologia,
                "producto": producto_txt or None,
                "herramienta": herramienta_txt or None,
                "elementos_tabla": elementos_tabla or None
            })

        # Detalle por subárea
        detalles.append({
            "tarea_id": t.tarea_id,
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "sop_codigo": sop.sop_codigo,
            "observacion_critica": sop.observacion_critica_sop if sop else None,
            "fracciones": fracciones_filtradas
        })

    # Renderizar plantilla
    return render_template("reporte_personal.html", persona=persona, fecha=fecha_obj, detalles=detalles)




# =========================
# REPORTE Persona PDF MACRO
# =========================
@main_bp.route('/reporte/<fecha>/<personal_id>/pdf')
def reporte_persona_dia_pdf(fecha, personal_id):
    """
    PDF MACRO — SOP completo de la persona (todas las subáreas y fracciones filtradas por nivel).
    """
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

    nivel_map = {"basica": 1, "media": 2, "profunda": 3}

    for t in tareas:
        area = Area.query.get(t.area_id)
        subarea = SubArea.query.get(t.subarea_id)
        if not subarea or not area:
            continue

        sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first()
        if not sop:
            continue

        nivel_asignado = (t.nivel_limpieza_asignado or "").strip().lower()
        nivel_id = nivel_map.get(nivel_asignado)
        if not nivel_id:
            continue

        fracciones = Fraccion.query.filter_by(sop_id=sop.sop_id).order_by(Fraccion.orden).all()
        fracciones_filtradas = []

        for f in fracciones:
            fd = FraccionDetalle.query.filter_by(fraccion_id=f.fraccion_id, nivel_limpieza_id=nivel_id).first()
            if not fd:
                continue

            metodologia = Metodologia.query.get(fd.metodologia_id)
            nivel_obj = NivelLimpieza.query.get(fd.nivel_limpieza_id)

            fracciones_filtradas.append({
                "orden": f.orden,
                "fraccion_nombre": f.fraccion_nombre,
                "descripcion": f.descripcion or (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_obj.nombre if nivel_obj else "",
                "metodologia_nombre": metodologia.nombre if metodologia else "",
                "tiempo_base": f.tiempo_base_min,
                "tipo_formula": f.tipo_formula,
                "ajuste_factor": fd.ajuste_factor
            })

        detalles.append({
            "area": area.area_nombre,
            "subarea": subarea.subarea_nombre,
            "nivel": nivel_asignado,
            "sop_codigo": sop.sop_codigo if sop else None,
            "observacion_critica": sop.observacion_critica_sop if sop else None,
            "fracciones": fracciones_filtradas
        })

    # Ordenar por área, subárea
    detalles.sort(key=lambda d: (d["area"], d["subarea"]))

    html = render_template("reporte_personal_dia.html",
                           persona=persona, fecha=fecha_obj, reporte_data=detalles)

    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=PDF_OPTIONS)
    return make_response((pdf_bytes, 200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename=SOP_{personal_id}_{fecha}.pdf"
    }))



# =========================
# REPORTE Persona PDF MICRO
# =========================
@main_bp.route('/tarea/<int:tarea_id>/pdf')
def reporte_tarea_pdf(tarea_id):
    """
    PDF MICRO — genera un reporte de una sola subárea/tarea con fracciones y metodología.
    """
    t = LanzamientoTarea.query.get_or_404(tarea_id)
    persona = getattr(t, "personal", None) or Personal.query.filter_by(personal_id=t.personal_id).first()
    area = Area.query.get(t.area_id)
    subarea = SubArea.query.get(t.subarea_id)
    sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first() if subarea else None

    nivel_map = {"basica": 1, "media": 2, "profunda": 3}
    nivel_asignado = (t.nivel_limpieza_asignado or "").strip().lower()
    nivel_id = nivel_map.get(nivel_asignado)
    fracciones_filtradas = []

    if sop and nivel_id:
        fracciones = Fraccion.query.filter_by(sop_id=sop.sop_id).order_by(Fraccion.orden).all()

        for f in fracciones:
            fd = FraccionDetalle.query.filter_by(fraccion_id=f.fraccion_id, nivel_limpieza_id=nivel_id).first()
            if not fd:
                continue

            metodologia = Metodologia.query.get(fd.metodologia_id)
            nivel_obj = NivelLimpieza.query.get(fd.nivel_limpieza_id)

            fracciones_filtradas.append({
                "orden": f.orden,
                "fraccion_nombre": f.fraccion_nombre,
                "descripcion": f.descripcion or (metodologia.descripcion if metodologia else ""),
                "nivel_limpieza": nivel_obj.nombre if nivel_obj else "",
                "metodologia_nombre": metodologia.nombre if metodologia else "",
                "tiempo_base": f.tiempo_base_min,
                "tipo_formula": f.tipo_formula,
                "ajuste_factor": fd.ajuste_factor
            })

    html = render_template("reporte_personal_dia.html",  # usa el mismo template
                           persona=persona,
                           fecha=date.today(),
                           reporte_data=[{
                               "area": area.area_nombre,
                               "subarea": subarea.subarea_nombre,
                               "nivel": nivel_asignado,
                               "sop_codigo": sop.sop_codigo if sop else None,
                               "observacion_critica": sop.observacion_critica_sop if sop else None,
                               "fracciones": fracciones_filtradas
                           }])

    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=PDF_OPTIONS)
    return make_response((pdf_bytes, 200, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f"attachment; filename=SOP_{t.personal_id}_{subarea.subarea_nombre}.pdf"
    }))


# =========================
# Calcular Tiempo Tarea
# =========================
# import necesario arriba del archivo routes.py
def calcular_tiempo_tarea(tarea):
    """
    Nuevo cálculo de tiempo por tarea:
      - busca las fracciones del SOP de la subárea
      - intenta localizar FraccionDetalle para cada fracción + nivel
      - usa la formula:
         tiempo_total = tiempo_base_min * superficie * ajuste_factor * factor_nivel
      - si tipo_formula == 'fijo' -> no multiplicar por superficie
    Retorna minutos totales (float) sumando todas las fracciones aplicables.
    """

    # obtener subarea y superficie (fallback a 1.0 si no existe)
    subarea = getattr(tarea, "subarea", None) or SubArea.query.get(tarea.subarea_id)
    superficie = float(getattr(subarea, "superficie_subarea", 0) or 0)
    if superficie <= 0:
        # si no hay superficie en DB, asumimos 1 para fórmulas fijas/por pieza
        superficie = 1.0

    # obtener nivel asignado y su factor (fallback 1.0)
    nivel_text = (tarea.nivel_limpieza_asignado or "").strip().lower()
    nivel_obj = None
    factor_nivel = 1.0
    # intento buscar por nombre o por id (según cómo lo guardes)
    # preferible que la tabla NivelLimpieza tenga 'nombre' con "basica","media","profunda"
    if nivel_text:
        nivel_obj = NivelLimpieza.query.filter(
            NivelLimpieza.nombre.ilike(nivel_text)
        ).first()
    if not nivel_obj and getattr(tarea, "nivel_limpieza_asignado", None):
        # fallback: buscar por id si guardas nivel_limpieza_id en tarea (no aplicable hoy pero por si acaso)
        try:
            nivel_obj = NivelLimpieza.query.get(int(tarea.nivel_limpieza_asignado))
        except Exception:
            nivel_obj = None
    if nivel_obj:
        factor_nivel = float(nivel_obj.factor_nivel or 1.0)

    # localizar SOP de la subarea
    sop = SOP.query.filter_by(subarea_id=subarea.subarea_id).first() if subarea else None
    if not sop:
        return 0.0

    # traer fracciones (ordenadas)
    fracciones = Fraccion.query.filter_by(sop_id=sop.sop_id).order_by(Fraccion.orden).all()

    total_min = 0.0

    for f in fracciones:
        tiempo_base = float(getattr(f, "tiempo_base_min", 0) or 0)
        tipo_formula = (getattr(f, "tipo_formula", "") or "").lower()

        # intentar obtener FraccionDetalle que coincida con este fraccion + nivel asignado
        fd = None
        if nivel_obj:
            fd = FraccionDetalle.query.filter_by(
                fraccion_id=f.fraccion_id,
                nivel_limpieza_id=nivel_obj.nivel_limpieza_id
            ).first()

        ajuste = 1.0
        if fd:
            ajuste = float(getattr(fd, "ajuste_factor", 1.0) or 1.0)

        # calcular superficie aplicable según tipo_formula
        if tipo_formula in ("por_m2", "por_m²", "por_m2"):
            superficie_app = superficie
        elif tipo_formula == "por_pieza":
            # en este caso, esperamos que 'superficie' represente cantidad de piezas,
            # si no, se usará 1
            superficie_app = max(1.0, superficie)
        else:  # 'fijo' u otro -> no multiplicar
            superficie_app = 1.0

        # fórmula principal
        tiempo_fraccion_total = tiempo_base * superficie_app * ajuste * factor_nivel

        total_min += float(tiempo_fraccion_total or 0)

    return round(total_min, 2)

 


# =========================
# Calcular Tiempo Tarea
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
        nivel_limpieza_asignado=nivel
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
                crear_tarea(fecha_dest, t.personal_id, t.area_id, t.subarea_id, t.nivel_limpieza_asignado)
    db.session.commit()

def aplicar_plantilla_guardada(plantilla_id: int, destino_lunes: date, overwrite: bool):
    if overwrite:
        borrar_asignaciones_semana(destino_lunes)

    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    for it in plantilla.items:
        fecha_dest = destino_lunes + timedelta(days=it.dia_index)
        if not existe_tarea(fecha_dest, it.personal_id, it.subarea_id):
            crear_tarea(fecha_dest, it.personal_id, it.area_id, it.subarea_id, it.nivel_limpieza_asignado)
    db.session.commit()


# ====== UI: GET formulario de aplicación de plantilla ======
@main_bp.route('/plantillas/aplicar')
def plantillas_aplicar_form():
    # Por ahora usamos la semana visible en Home: la actual
    hoy = date.today()
    lunes_destino = get_monday(hoy)
    # plantillas disponibles
    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    # semana anterior como sugerencia
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

    # Vuelve al home para ver el resultado
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
                nivel_limpieza_asignado=t.nivel_limpieza_asignado
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
                    nivel_limpieza_asignado=t.nivel_limpieza_asignado
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
                nivel_limpieza_asignado=t.nivel_limpieza_asignado
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
        borrar_asignaciones_semana(lunes_destino)     # 🔴 borra Lun–Sáb
        set_plantilla_activa(lunes_destino, None)     # etiqueta = Ninguna
        flash('Semana vaciada. Plantilla activa: Ninguna.', 'success')
        return redirect(url_for('main.home'))

    # 2) Si eligen una plantilla: reemplazo total
    plantilla_id = int(plantilla_id_str)

    # 🔴 borra Lun–Sáb de destino ANTES de aplicar
    borrar_asignaciones_semana(lunes_destino)

    # ✅ aplica plantilla (como ya la tienes) — no hace falta overwrite porque ya está limpia
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

