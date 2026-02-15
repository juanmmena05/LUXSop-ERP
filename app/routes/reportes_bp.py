# reportes_bp.py - Blueprint para reportes
from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, make_response, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

from .helpers import (
    admin_required, canon_nivel, nivel_to_id,
    na, fmt_consumo, fmt_herramientas_list, fmt_quimico_y_receta,
    pdfkit, PDFKIT_CONFIG, PDF_OPTIONS, today_cdmx
)
from ..extensions import db
from ..models import (
    Personal, LanzamientoDia, LanzamientoTarea, TareaCheck,
    SOP, SopFraccion, SopFraccionDetalle,
    SopEvento, SopEventoDetalle, SopEventoFraccion,
    MetodologiaEventoFraccion,
    Kit, KitDetalle, Receta, RecetaDetalle,
    ElementoSet, ElementoDetalle,
    Fraccion, InstructivoTrabajo,
)

reportes_bp = Blueprint("reportes", __name__)


def build_met_map(fraccion_ids, nivel_ids):
    """Construye mapa de metodologías para fracciones y niveles."""
    from ..models import Metodologia, MetodologiaBase

    if not fraccion_ids or not nivel_ids:
        return {}

    metodologias = (
        Metodologia.query
        .filter(
            Metodologia.fraccion_id.in_(fraccion_ids),
            Metodologia.nivel_limpieza_id.in_(nivel_ids)
        )
        .options(
            joinedload(Metodologia.metodologia_base)
            .selectinload(MetodologiaBase.pasos)
        )
        .all()
    )

    return {(m.fraccion_id, m.nivel_limpieza_id): m.metodologia_base for m in metodologias}


@reportes_bp.route("/reporte/<fecha>/<personal_id>")
@login_required
def reporte_persona_dia(fecha, personal_id):
    """Reporte HTML de tareas del día para una persona."""

    # Determinar si el usuario puede hacer checks
    puede_hacer_check = False
    es_hoy = (fecha == today_cdmx().strftime("%Y-%m-%d"))

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
            joinedload(LanzamientoTarea.personal),
            joinedload(LanzamientoTarea.area),
            joinedload(LanzamientoTarea.subarea),
            joinedload(LanzamientoTarea.sop),
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
    tareas_fijas = [t for t in tareas if t.tipo_tarea in ('inicio', 'receso')]
    tareas_evento = [t for t in tareas if t.tipo_tarea == 'evento']

    # ===== PROCESAR SOPs =====
    sop_ids = list({t.sop_id for t in tareas_sop if t.sop_id})
    subarea_ids_sin_sop = list({t.subarea_id for t in tareas_sop if not t.sop_id and t.subarea_id})

    detalles = []

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
                selectinload(SOP.sop_fracciones).selectinload(SopFraccion.fraccion).selectinload(Fraccion.instructivo),
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

        # Procesar SOPs
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
                    "fraccion_id": fr.fraccion_id if fr else None,  # ← AGREGAR
                    "nombre_full": fr.nombre_full if fr else "",
                    "descripcion": metodologia.descripcion or "",
                    "nivel_limpieza": nivel_asignado,
                    "tiempo_min": round(tiempo_min, 2) if tiempo_min is not None else None,
                    "metodologia": metodologia,
                    "tabla": tabla,
                    "observacion_critica": (fr.nota_tecnica if fr else None),
                    "instructivo": fr.instructivo if fr and fr.instructivo else None,  # ← AGREGAR
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

    # ===== PROCESAR TAREAS FIJAS =====
    for t in tareas_fijas:
        tipo_nombre = {
            'inicio': 'INICIO',
            'receso': 'RECESO',
        }.get(t.tipo_tarea, t.tipo_tarea.upper())

        if t.sop_evento_id and t.sop_evento:
            sop_evento = t.sop_evento
            tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)

            fracciones_evento = []
            for detalle in sop_evento.detalles:
                fraccion = detalle.fraccion
                metodologia = fraccion.metodologia if fraccion else None

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
                    "nombre_full": fraccion.nombre if fraccion else "",
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
            tiempo_fijo = {'receso': 45}.get(t.tipo_tarea, 0)

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

    # ===== PROCESAR EVENTOS =====
    for t in tareas_evento:
        sop_evento = t.sop_evento
        if not sop_evento:
            continue

        caso_nombre = sop_evento.caso_catalogo.nombre
        evento_nombre = sop_evento.evento_catalogo.nombre
        area_nombre = t.area.area_nombre if t.area else "Sin área"

        tiempo_total = sum(detalle.tiempo_estimado for detalle in sop_evento.detalles)

        fracciones_evento = []
        for detalle in sop_evento.detalles:
            fraccion = detalle.fraccion
            metodologia = fraccion.metodologia if fraccion else None

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
                "nombre_full": fraccion.nombre if fraccion else "",
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
        "reportes/reporte_personal.html",
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


@reportes_bp.route("/reporte/<fecha>/<personal_id>/pdf")
@login_required
def reporte_persona_dia_pdf(fecha, personal_id):
    """Genera PDF del reporte de tareas del día."""

    if (pdfkit is None) or (PDFKIT_CONFIG is None):
        flash("PDF no disponible en este servidor (wkhtmltopdf no está instalado).", "warning")
        return redirect(url_for("rutas.mi_ruta"))

    if current_user.role != "admin":
        if current_user.personal_id != personal_id:
            abort(403)
        if fecha != today_cdmx().strftime("%Y-%m-%d"):
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
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.kit).joinedload(Kit.detalles).joinedload(KitDetalle.herramienta),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.receta).joinedload(Receta.detalles).joinedload(RecetaDetalle.quimico),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.consumo),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.elemento_set).joinedload(ElementoSet.detalles).joinedload(ElementoDetalle.elemento),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.elemento_set).joinedload(ElementoSet.detalles).joinedload(ElementoDetalle.receta).joinedload(Receta.detalles).joinedload(RecetaDetalle.quimico),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.elemento_set).joinedload(ElementoSet.detalles).joinedload(ElementoDetalle.kit).joinedload(Kit.detalles).joinedload(KitDetalle.herramienta),
                joinedload(SOP.sop_fracciones).joinedload(SopFraccion.detalles).joinedload(SopFraccionDetalle.elemento_set).joinedload(ElementoSet.detalles).joinedload(ElementoDetalle.consumo),
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
                tiempo_total_min += tiempo_min

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
            "tiempo_total_min": round(tiempo_total_min, 2),
            "observacion_critica": sop.observacion_critica_sop,
            "fracciones": fracciones_filtradas,
            "orden": t.orden if t.orden is not None else 0,
            "orden_area": area.orden_area if area.orden_area is not None else 9999,
            "orden_subarea": subarea.orden_subarea if subarea.orden_subarea is not None else 9999
        })

    if not detalles:
        return f"No fue posible generar el PDF para {personal_id} en {fecha} (sin detalles).", 404

    detalles.sort(key=lambda d: (d.get("orden", 0), d.get("orden_area", 9999), d.get("orden_subarea", 9999)))

    html = render_template("reportes/sop_macro_pdf.html", persona=persona, fecha=fecha_obj, detalles=detalles)

    try:
        pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=PDF_OPTIONS)
    except Exception as e:
        flash(f"No se pudo generar el PDF: {e}", "warning")
        return redirect(url_for("rutas.mi_ruta"))

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename=SOP_{personal_id}_{fecha}.pdf"
    return resp
