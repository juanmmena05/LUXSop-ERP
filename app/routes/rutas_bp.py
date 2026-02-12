# rutas_bp.py - Blueprint de rutas diarias, plan y asignaciones
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from .helpers import (
    admin_required, get_monday, get_or_create_dia, canon_nivel, nivel_to_id,
    asegurar_tareas_fijas, calcular_tiempo_tarea, today_cdmx
)
from ..extensions import db
from ..models import (
    Area, SubArea, SOP, Personal,
    LanzamientoDia, LanzamientoTarea, AsignacionPersonal,
    TareaCheck, PlantillaItem,
    SopFraccion, SopEvento, SopEventoDetalle,
    Kit, Receta,
)

rutas_bp = Blueprint("rutas", __name__)


@rutas_bp.route("/mi_ruta")
@login_required
def mi_ruta():
    # Si es admin, no debe entrar aquí
    if getattr(current_user, "role", None) == "admin":
        return redirect(url_for("home.home_admin_panel"))

    # Operativo debe estar ligado a un Personal
    if not getattr(current_user, "personal_id", None):
        abort(403)

    hoy = today_cdmx()
    hoy_str = hoy.strftime("%Y-%m-%d")

    dia = LanzamientoDia.query.filter_by(fecha=hoy).first()

    tareas = []
    tiempo_total = 0.0
    checks_map = {}

    if dia:
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

        tarea_ids = [t.tarea_id for t in tareas]
        if tarea_ids:
            checks = TareaCheck.query.filter(TareaCheck.tarea_id.in_(tarea_ids)).all()
            checks_map = {c.tarea_id: c.checked_at.strftime("%H:%M") for c in checks}

        try:
            tiempo_total = sum(float(calcular_tiempo_tarea(t)) for t in tareas)
        except Exception:
            tiempo_total = 0.0

    total_tareas = len(tareas)
    completadas = len(checks_map)
    progreso_pct = round((completadas / total_tareas * 100) if total_tareas > 0 else 0)

    return render_template(
        "rutas/mi_ruta.html",
        hoy=hoy,
        hoy_str=hoy_str,
        tareas=tareas,
        tiempo_total=round(tiempo_total, 2),
        checks_map=checks_map,
        total_tareas=total_tareas,
        completadas=completadas,
        progreso_pct=progreso_pct,
    )


@rutas_bp.route("/personal/<personal_id>/asignar", methods=["GET", "POST"])
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
            return redirect(url_for("rutas.asignar_ruta", personal_id=personal_id))

        db.session.add(AsignacionPersonal(
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado,
        ))
        db.session.commit()
        return redirect(url_for("rutas.asignar_ruta", personal_id=personal_id))

    asignaciones = AsignacionPersonal.query.filter_by(personal_id=personal_id).all()
    return render_template(
        "rutas/asignacion_form.html",
        persona=persona, areas=areas, subareas=subareas, asignaciones=asignaciones
    )


@rutas_bp.route("/plan/<fecha>/borrar/<int:tarea_id>", methods=["POST"])
@admin_required
def borrar_tarea(fecha, tarea_id):
    try:
        tarea = LanzamientoTarea.query.get_or_404(tarea_id)

        check = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
        if check:
            db.session.delete(check)

        db.session.delete(tarea)
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Tarea eliminada'})

        flash("Tarea eliminada correctamente.", "success")
        return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f"Error al eliminar: {str(e)}", "danger")
        return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))


@rutas_bp.route("/subareas_por_area/<area_id>")
def subareas_por_area(area_id):
    fecha_str = request.args.get("fecha")
    if fecha_str:
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    else:
        fecha_obj = today_cdmx()

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


@rutas_bp.route("/subareas_por_area_simple/<area_id>")
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


@rutas_bp.route("/plan/<fecha>/asignar", methods=["GET", "POST"])
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

        es_adicional_str = request.form.get("es_adicional", "0")
        es_adicional = es_adicional_str == "1"
        tipo_sop_form = (request.form.get("tipo_sop") or "regular").strip().lower()

        if tipo_sop_form == "extraordinario":
            tipo_sop = "regular"
            nivel_limpieza_asignado = "extraordinario"
        elif tipo_sop_form == "consecuente":
            tipo_sop = "consecuente"
            nivel_limpieza_asignado = "basica"
        else:
            tipo_sop = "regular"

        if not nivel_limpieza_asignado:
            flash("Nivel de limpieza inválido.", "warning")
            return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

        if not es_adicional:
            existe_misma_subarea = LanzamientoTarea.query.filter_by(
                dia_id=dia.dia_id,
                subarea_id=subarea_id,
                es_adicional=False
            ).first()
            if existe_misma_subarea:
                flash("Esa subárea ya tiene una tarea REGULAR asignada en este día.", "warning")
                return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

        sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()
        if not sop:
            tipo_nombre = "Regular" if tipo_sop == "regular" else "Consecuente"
            flash(f"No existe SOP {tipo_nombre} para esta subárea.", "warning")
            return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

        if tipo_sop != "consecuente":
            existe_mismo_sop = LanzamientoTarea.query.filter_by(
                dia_id=dia.dia_id,
                subarea_id=subarea_id,
                sop_id=sop.sop_id
            ).first()
            if existe_mismo_sop:
                if nivel_limpieza_asignado == "extraordinario":
                    flash(f"Ya existe una tarea Regular/Extraordinario para esta subárea.", "warning")
                else:
                    flash(f"Ya existe una tarea Regular para esta subárea en este día.", "warning")
                return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

        t = LanzamientoTarea(
            dia_id=dia.dia_id,
            personal_id=personal_id,
            area_id=area_id,
            subarea_id=subarea_id,
            nivel_limpieza_asignado=nivel_limpieza_asignado,
            sop_id=sop.sop_id,
            es_adicional=es_adicional,
            tipo_tarea='sop',
            es_arrastrable=True
        )
        db.session.add(t)
        asegurar_tareas_fijas(dia.dia_id, personal_id)

        db.session.commit()

        return redirect(url_for("rutas.plan_dia_asignar", fecha=fecha))

    # GET
    tareas_del_dia = (
        LanzamientoTarea.query
        .filter_by(dia_id=dia.dia_id)
        .options(
            joinedload(LanzamientoTarea.personal),
            joinedload(LanzamientoTarea.area),
            joinedload(LanzamientoTarea.subarea),
            joinedload(LanzamientoTarea.sop).selectinload(SOP.sop_fracciones).selectinload(SopFraccion.detalles),
            joinedload(LanzamientoTarea.sop_evento).selectinload(SopEvento.detalles)
        )
        .all()
    )

    tiempos_por_tarea = {t.tarea_id: calcular_tiempo_tarea(t) for t in tareas_del_dia}

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
        "rutas/plan_dia_form.html",
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


@rutas_bp.route("/plan/<fecha>/ruta")
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

    return render_template("rutas/ruta_dia.html", fecha=fecha_obj, personas=personas, hide_nav=True)


@rutas_bp.route("/api/reordenar-tareas", methods=["POST"])
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


@rutas_bp.route("/api/reordenar-plantilla-items", methods=["POST"])
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
