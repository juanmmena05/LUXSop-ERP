# plantillas_bp.py - Blueprint para gestión de plantillas
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from .helpers import (
    admin_required, canon_nivel, get_monday,
    borrar_asignaciones_semana, aplicar_plantilla_guardada, set_plantilla_activa,
    today_cdmx
)
from ..extensions import db
from ..models import (
    Personal, Area, SubArea, SOP,
    LanzamientoDia, LanzamientoTarea,
    PlantillaSemanal, PlantillaItem, PlantillaSemanaAplicada,
)

plantillas_bp = Blueprint("plantillas", __name__)


@plantillas_bp.route("/plantillas")
@admin_required
def plantillas_panel():
    """Panel principal de plantillas."""
    if current_user.role != "admin":
        abort(403)

    hoy = today_cdmx()
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
        for it in (plantilla.items or []):
            if it.dia_index is None:
                continue
            if 0 <= int(it.dia_index) <= 5:
                dias[int(it.dia_index)]["items"].append(it)

        for d in dias:
            d["items"].sort(key=lambda x: (x.personal_id or "", x.area_id or "", x.subarea_id or ""))

    return render_template(
        "plantillas/plantillas_panel.html",
        plantillas=plantillas,
        plantilla=plantilla,
        dias=dias,
        lunes_ref=lunes_ref.strftime("%Y-%m-%d"),
    )


@plantillas_bp.route("/plantillas/guardar_simple", methods=["POST"])
@admin_required
def guardar_semana_como_plantilla_simple():
    """Guarda la semana visible como plantilla."""
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
            return redirect(url_for("home.home"))

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
        return redirect(url_for("home.home"))

    # Caso B: crear nueva plantilla
    if not nombre:
        flash("Escribe un nombre para la nueva plantilla.", "warning")
        return redirect(url_for("home.home"))

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("home.home"))

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
    return redirect(url_for("home.home"))


@plantillas_bp.route("/plantillas/aplicar_simple", methods=["POST"])
@admin_required
def aplicar_plantilla_guardada_simple():
    """Aplica plantilla con confirmación."""
    lunes_destino_str = request.form.get("lunes_destino")
    plantilla_id_str = request.form.get("plantilla_id")
    confirmar = request.form.get("confirmar", type=int, default=0)

    if not lunes_destino_str or not plantilla_id_str:
        flash("Faltan datos", "warning")
        return redirect(url_for("home.home_admin_panel"))

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()
    plantilla_id = int(plantilla_id_str)

    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    plantilla_activa = PlantillaSemanaAplicada.query.get(lunes_destino)

    if not confirmar:
        if plantilla_activa and plantilla_activa.plantilla:
            mensaje = f"¿Estás seguro de cambiar a <strong>{plantilla.nombre}</strong>?"
            detalle = "Esto borrará todas las tareas actuales y aplicará la nueva plantilla desde cero."
        else:
            mensaje = f"¿Estás seguro de aplicar la plantilla <strong>{plantilla.nombre}</strong>?"
            detalle = f"Se agregarán las tareas programadas a la semana."

        return render_template(
            "components/confirmacion_modal.html",
            titulo="Confirmar Aplicación",
            mensaje=mensaje,
            detalle=detalle,
            form_action=url_for("plantillas.aplicar_plantilla_guardada_simple"),
            form_data={
                "lunes_destino": lunes_destino_str,
                "plantilla_id": plantilla_id,
                "confirmar": 1
            },
            cancelar_url=url_for("home.home_admin_panel")
        )

    borrar_asignaciones_semana(lunes_destino)
    aplicar_plantilla_guardada(plantilla_id, lunes_destino, overwrite=False)
    set_plantilla_activa(lunes_destino, plantilla_id)

    flash(f"Plantilla '{plantilla.nombre}' aplicada correctamente.", "success")
    return redirect(url_for("home.home_admin_panel"))


@plantillas_bp.route("/plantillas/borrar/<int:plantilla_id>", methods=["POST"])
@admin_required
def borrar_plantilla(plantilla_id):
    """Elimina una plantilla."""
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    PlantillaItem.query.filter_by(plantilla_id=plantilla_id).delete()
    db.session.delete(plantilla)
    db.session.commit()
    flash(f'Plantilla "{plantilla.nombre}" eliminada correctamente.', "success")
    return redirect(url_for("home.home"))


@plantillas_bp.route("/plantillas/vaciar_semana", methods=["POST"])
@admin_required
def vaciar_semana():
    """Vacía todas las tareas de una semana."""
    lunes_destino_str = request.form.get("lunes_destino")
    confirmar = request.form.get("confirmar", type=int, default=0)

    if not lunes_destino_str:
        flash("Falta fecha", "warning")
        return redirect(url_for("home.home_admin_panel"))

    lunes_destino = datetime.strptime(lunes_destino_str, "%Y-%m-%d").date()

    if not confirmar:
        return render_template(
            "components/confirmacion_modal.html",
            titulo="Confirmar Vaciado",
            mensaje="¿Estás seguro de vaciar la semana?",
            detalle="Esto borrará todas las tareas y desactivará la plantilla.",
            form_action=url_for("plantillas.vaciar_semana"),
            form_data={
                "lunes_destino": lunes_destino_str,
                "confirmar": 1
            },
            cancelar_url=url_for("home.home_admin_panel")
        )

    borrar_asignaciones_semana(lunes_destino)
    set_plantilla_activa(lunes_destino, None)

    flash("Semana vaciada. Plantilla desactivada.", "success")
    return redirect(url_for("home.home_admin_panel"))


@plantillas_bp.route("/plantillas/crear", methods=["POST"])
@admin_required
def plantillas_crear():
    """Crea una plantilla vacía."""
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        flash("Escribe un nombre para la plantilla.", "warning")
        return redirect(url_for("plantillas.plantillas_panel"))

    if PlantillaSemanal.query.filter_by(nombre=nombre).first():
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("plantillas.plantillas_panel"))

    plantilla = PlantillaSemanal(nombre=nombre)
    db.session.add(plantilla)
    db.session.commit()

    flash(f'Plantilla "{plantilla.nombre}" creada. Ahora puedes llenarla.', "success")
    return redirect(url_for("plantillas.plantillas_panel", plantilla_id=plantilla.plantilla_id))


@plantillas_bp.route("/plantillas/<int:plantilla_id>/item/add", methods=["POST"])
@admin_required
def plantilla_item_add(plantilla_id: int):
    """Agrega item a un día de una plantilla."""
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

    dia_index = request.form.get("dia_index")
    personal_id = request.form.get("personal_id")
    area_id = request.form.get("area_id")
    subarea_id = request.form.get("subarea_id")

    es_adicional_str = request.form.get("es_adicional", "0")
    es_adicional = es_adicional_str == "1"
    tipo_sop_form = (request.form.get("tipo_sop") or "regular").strip().lower()
    nivel = canon_nivel(request.form.get("nivel_limpieza_asignado")) or "basica"

    if dia_index is None or not str(dia_index).isdigit():
        flash("Día inválido.", "warning")
        return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=0))

    dia_index = int(dia_index)
    if dia_index < 0 or dia_index > 5:
        flash("Día inválido (0..5).", "warning")
        return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=0))

    if not (personal_id and area_id and subarea_id):
        flash("Faltan datos (personal/área/subárea).", "warning")
        return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    if tipo_sop_form == "extraordinario":
        tipo_sop = "regular"
        nivel = "extraordinario"
    elif tipo_sop_form == "consecuente":
        tipo_sop = "consecuente"
        nivel = "basica"
    else:
        tipo_sop = "regular"

    if not es_adicional:
        existe_misma_subarea = PlantillaItem.query.filter_by(
            plantilla_id=plantilla_id,
            dia_index=dia_index,
            subarea_id=subarea_id,
            es_adicional=False
        ).first()
        if existe_misma_subarea:
            flash("Esa subárea ya tiene una tarea REGULAR en este día de la plantilla.", "warning")
            return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()
    if not sop:
        tipo_nombre = "Regular" if tipo_sop == "regular" else "Consecuente"
        flash(f"No existe SOP {tipo_nombre} para esta subárea.", "warning")
        return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

    if tipo_sop == "consecuente":
        pass
    else:
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
            return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))

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
    return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))


@plantillas_bp.route("/plantillas/item/<int:item_id>/delete", methods=["POST"])
@admin_required
def plantilla_item_delete(item_id: int):
    """Elimina un item de plantilla."""
    it = PlantillaItem.query.get_or_404(item_id)
    plantilla_id = it.plantilla_id
    dia_index = it.dia_index
    db.session.delete(it)
    db.session.commit()
    flash("Actividad eliminada.", "success")
    return redirect(url_for("plantillas.plantilla_dia", plantilla_id=plantilla_id, dia_index=dia_index))


@plantillas_bp.route("/plantillas/<int:plantilla_id>/rename", methods=["POST"])
@admin_required
def plantilla_rename(plantilla_id: int):
    """Renombra una plantilla."""
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        flash("Nombre inválido.", "warning")
        return redirect(url_for("plantillas.plantillas_panel", plantilla_id=plantilla_id))

    dup = PlantillaSemanal.query.filter(
        PlantillaSemanal.nombre == nombre,
        PlantillaSemanal.plantilla_id != plantilla_id
    ).first()
    if dup:
        flash("Ya existe una plantilla con ese nombre.", "warning")
        return redirect(url_for("plantillas.plantillas_panel", plantilla_id=plantilla_id))

    plantilla.nombre = nombre
    db.session.commit()
    flash("Nombre actualizado.", "success")
    return redirect(url_for("plantillas.plantillas_panel", plantilla_id=plantilla_id))


@plantillas_bp.route("/plantillas/<int:plantilla_id>/dia/<int:dia_index>")
@admin_required
def plantilla_dia(plantilla_id: int, dia_index: int):
    """Editor de día de plantilla."""
    plantilla = PlantillaSemanal.query.get_or_404(plantilla_id)

    if dia_index < 0 or dia_index > 5:
        abort(404)

    day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    dia_nombre = day_names[dia_index]

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

    items_regulares = [it for it in items if not getattr(it, 'es_adicional', False)]
    asignadas_regular_ids = {it.subarea_id for it in items_regulares}

    personal_list = Personal.query.order_by(Personal.nombre.asc()).all()
    areas_list = Area.query.order_by(Area.orden_area.asc(), Area.area_nombre.asc()).all()
    subareas_list = SubArea.query.order_by(SubArea.orden_subarea.asc()).all()

    items_por_persona = {}
    for it in items:
        pid = it.personal_id
        if pid not in items_por_persona:
            items_por_persona[pid] = {"persona": it.personal, "items": []}
        items_por_persona[pid]["items"].append(it)

    for pid in items_por_persona:
        items_por_persona[pid]["items"].sort(key=lambda x: (
            x.orden or 0,
            x.area.orden_area if x.area else 9999,
            x.subarea.orden_subarea if x.subarea else 9999
        ))

    return render_template(
        "rutas/plantilla_dia_form.html",
        plantilla=plantilla,
        dia_index=dia_index,
        dia_nombre=dia_nombre,
        personal_list=personal_list,
        areas_list=areas_list,
        subareas_list=subareas_list,
        asignadas_ids=asignadas_regular_ids,
        asignadas_regular_ids=asignadas_regular_ids,
        items_por_persona=items_por_persona,
        hide_nav=True,
    )
