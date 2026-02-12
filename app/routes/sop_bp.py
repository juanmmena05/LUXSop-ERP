# sop_bp.py - Blueprint para gestión de SOP (Standard Operating Procedures)
#
# Rutas:
# - sop_panel: Panel principal SOP regular y evento
# - sop_detalles: Edición de detalles por fracción/nivel
# - sop_fracciones_edit: Redirección a edición de fracciones
# - sop_crear: Crear/editar SOP seleccionando fracciones
# - sop_elementoset_edit: Editar elementos de un set
# - sop_evento_crear: Crear SOP de evento
# - sop_evento_editar: Editar SOP de evento
# - sop_evento_detalle: Editar detalle de SOP evento

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, or_

from ..models import (
    db, SOP, SubArea, Area, Fraccion, NivelLimpieza,
    SopFraccion, SopFraccionDetalle, Metodologia, MetodologiaBase,
    ElementoSet, ElementoDetalle, Elemento, Kit, Receta, Consumo,
    SopEvento, SopEventoFraccion, SopEventoDetalle,
    EventoCatalogo, CasoCatalogo
)
from .helpers import admin_required, nivel_to_id, canon_nivel


sop_bp = Blueprint("sop", __name__)


# =========================
# HELPERS: Crear IDs SOP
# =========================
def _strip_prefix(x: str, prefix: str) -> str:
    return x[len(prefix):] if x and x.startswith(prefix) else x


def nivel_letter(nivel_id: int) -> str:
    return {1: "B", 2: "M", 3: "P", 4: "E"}.get(int(nivel_id), "B")


def make_sop_id(subarea_id: str, tipo_sop: str) -> str:
    """Genera sop_id: SP-{subarea_id}-R o SP-{subarea_id}-C"""
    sufijo = "R" if tipo_sop == "regular" else "C"
    return f"SP-{subarea_id}-{sufijo}"


def make_sf_id(sop_id: str, fraccion_id: str) -> str:
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"SF-{sop_core}-{fr_core}"


def make_sd_id(sop_id: str, fraccion_id: str, nivel_id: int) -> str:
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"SD-{sop_core}-{fr_core}-{nivel_letter(nivel_id)}"


def make_es_id(sop_id: str, fraccion_id: str, nivel_id: int) -> str:
    sop_core = _strip_prefix(sop_id, "SP-")
    fr_core = _strip_prefix(fraccion_id, "FR-")
    return f"ES-{sop_core}-{fr_core}-{nivel_letter(nivel_id)}"


# =========================
# SOP PANEL
# =========================
@sop_bp.route("/sop")
@admin_required
def sop_panel():
    # ============================================================================
    # PARTE 1: SOP REGULAR/CONSECUENTE
    # ============================================================================
    area_id = (request.args.get("area_id") or "").strip()
    subarea_id = (request.args.get("subarea_id") or "").strip()
    tipo_sop = (request.args.get("tipo_sop") or "regular").strip()

    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

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
    # PARTE 2: SOP EVENTO
    # ============================================================================
    evento_tipo_id = (request.args.get("evento_tipo_id") or "").strip()
    caso_id = (request.args.get("caso_id") or "").strip()

    eventos = EventoCatalogo.query.order_by(EventoCatalogo.nombre.asc()).all()

    casos = []
    if evento_tipo_id:
        casos = (
            CasoCatalogo.query
            .filter_by(evento_tipo_id=evento_tipo_id)
            .order_by(CasoCatalogo.nombre.asc())
            .all()
        )

    sop_evento = None
    has_fracciones_evento = False

    if evento_tipo_id and caso_id:
        sop_evento = SopEvento.query.filter_by(
            evento_tipo_id=evento_tipo_id,
            caso_id=caso_id
        ).first()

        if sop_evento and sop_evento.detalles and len(sop_evento.detalles) > 0:
            has_fracciones_evento = True

    return render_template(
        "sop/sop_panel.html",
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
        eventos=eventos,
        casos=casos,
        evento_tipo_id=evento_tipo_id,
        caso_id=caso_id,
        sop_evento=sop_evento,
        has_fracciones_evento=has_fracciones_evento,
    )


# =========================
# SOP DETALLES
# =========================
@sop_bp.route("/sop/<sop_id>/detalles", methods=["GET", "POST"])
@admin_required
def sop_detalles(sop_id):
    tipo_sop = (request.args.get("tipo_sop") or request.form.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    nivel = (request.args.get("nivel") or request.form.get("nivel") or "").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    nivel_obj = NivelLimpieza.query.filter_by(nombre=nivel).first()
    if not nivel_obj:
        flash("Nivel de limpieza inválido.", "error")
        return redirect(url_for("sop.sop_panel"))

    nivel_id = int(nivel_obj.nivel_limpieza_id)

    sop = SOP.query.filter_by(sop_id=sop_id).first_or_404()
    subarea = sop.subarea

    sop_fracciones_all = (
        SopFraccion.query
        .filter_by(sop_id=sop_id)
        .order_by(SopFraccion.orden.asc())
        .all()
    )

    if not sop_fracciones_all:
        flash("Este SOP no tiene fracciones todavía.", "warning")
        return redirect(url_for(
            "sop.sop_panel",
            area_id=subarea.area_id,
            subarea_id=subarea.subarea_id,
            nivel=nivel,
            tipo_sop=tipo_sop
        ))

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

    if not sop_fracciones_nivel:
        recetas = Receta.query.order_by(Receta.nombre.asc()).all()
        consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()
        kits = []
        return render_template(
            "sop/sop_detalles.html",
            sop=sop,
            subarea=subarea,
            nivel=nivel,
            nivel_id=nivel_id,
            nivel_obj=nivel_obj,
            tipo_sop=tipo_sop,
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

    sop_fracciones = sop_fracciones_nivel

    sop_fraccion_id = (request.args.get("sop_fraccion_id") or request.form.get("sop_fraccion_id") or "").strip()
    sf_actual = next((x for x in sop_fracciones if x.sop_fraccion_id == sop_fraccion_id), sop_fracciones[0])
    fr = sf_actual.fraccion

    recetas = Receta.query.order_by(Receta.nombre.asc()).all()
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()

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

    metodologia_base = None
    met = Metodologia.query.filter_by(fraccion_id=fr.fraccion_id, nivel_limpieza_id=nivel_id).first()
    if met and met.metodologia_base:
        metodologia_base = met.metodologia_base

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

    # POST: Guardar detalle
    if request.method == "POST":
        mode = (request.form.get("mode") or "directo").strip().lower()

        tiempo_raw = (request.form.get("tiempo_unitario_min") or "").strip()
        if tiempo_raw == "":
            detalle.tiempo_unitario_min = None
        else:
            try:
                detalle.tiempo_unitario_min = float(tiempo_raw)
            except ValueError:
                flash("Tiempo inválido.", "warning")
                return redirect(url_for("sop.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))

        if mode == "elementos":
            detalle.kit_id = None
            detalle.receta_id = None
            detalle.consumo_id = None

            es_id = (request.form.get("elemento_set_id") or "").strip() or None

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
                es_ok = ElementoSet.query.filter_by(
                    elemento_set_id=es_id,
                    subarea_id=subarea.subarea_id,
                    fraccion_id=fr.fraccion_id,
                    nivel_limpieza_id=nivel_id,
                ).first()
                if not es_ok:
                    flash("Elemento Set inválido para esta subárea/fracción/nivel.", "warning")
                    return redirect(url_for("sop.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))

            detalle.elemento_set_id = es_id
        else:
            detalle.elemento_set_id = None
            detalle.kit_id = (request.form.get("kit_id") or "").strip() or None
            detalle.receta_id = (request.form.get("receta_id") or "").strip() or None
            detalle.consumo_id = (request.form.get("consumo_id") or "").strip() or None

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("ERROR COMMIT sop_detalles:", repr(e))
            flash("Error guardando detalle (revisa consola).", "error")
            return redirect(url_for("sop.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))

        flash("Detalle guardado.", "success")
        return redirect(url_for("sop.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf_actual.sop_fraccion_id))

    return render_template(
        "sop/sop_detalles.html",
        sop=sop,
        subarea=subarea,
        nivel=nivel,
        nivel_id=nivel_id,
        nivel_obj=nivel_obj,
        tipo_sop=tipo_sop,
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


# =========================
# SOP FRACCIONES EDIT
# =========================
@sop_bp.route("/sop/<sop_id>/fracciones")
@admin_required
def sop_fracciones_edit(sop_id):
    nivel = (request.args.get("nivel") or "media").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    tipo_sop = (request.args.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    nivel_id = nivel_to_id(nivel) or 2

    sop = SOP.query.filter_by(sop_id=sop_id).first()
    if not sop:
        flash("SOP no encontrado.", "error")
        return redirect(url_for("sop.sop_panel"))

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
        return redirect(url_for("sop.sop_crear", subarea_id=sop.subarea_id, nivel=nivel, tipo_sop=tipo_sop))

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

    return redirect(url_for(
        "sop.sop_detalles",
        sop_id=sop_id,
        nivel=nivel,
        tipo_sop=tipo_sop,
        sop_fraccion_id=first_sf.sop_fraccion_id
    ))


# =========================
# SOP CREAR
# =========================
@sop_bp.route("/sop/crear/<subarea_id>", methods=["GET", "POST"])
@admin_required
def sop_crear(subarea_id):
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

    grupo_fracciones = subarea.area.grupo_fracciones if subarea.area else None
    sop_id = make_sop_id(subarea_id, tipo_sop)
    sop = SOP.query.filter_by(sop_id=sop_id).first()

    if sop:
        tipo_sop = sop.tipo_sop

    if nivel_id == 4:  # Extraordinario
        niveles_validos = [3, 4]
    else:
        niveles_validos = [nivel_id]

    fracciones_query = (
        Fraccion.query
        .join(Metodologia, Metodologia.fraccion_id == Fraccion.fraccion_id)
        .filter(Metodologia.nivel_limpieza_id.in_(niveles_validos))
        .distinct()
    )

    if grupo_fracciones:
        fracciones_query = fracciones_query.filter(Fraccion.grupo_fracciones == grupo_fracciones)

    fracciones = fracciones_query.order_by(Fraccion.fraccion_id.asc()).all()

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

    if request.method == "POST":
        selected = request.form.getlist("fraccion_id")
        selected_set = set(selected)

        if not selected:
            flash("Selecciona al menos 1 fracción.", "warning")
            return redirect(url_for("sop.sop_crear", subarea_id=subarea_id, nivel=nivel, tipo_sop=tipo_sop))

        if not sop:
            sop = SOP(
                sop_id=sop_id,
                subarea_id=subarea_id,
                tipo_sop=tipo_sop
            )
            db.session.add(sop)
            db.session.flush()
            tipo_sop = sop.tipo_sop

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
                for fr_id in to_remove:
                    es_id = make_es_id(sop.sop_id, fr_id, nivel_id)
                    es = ElementoSet.query.filter_by(elemento_set_id=es_id).first()
                    if es:
                        db.session.delete(es)

                SopFraccionDetalle.query.filter_by(
                    sop_fraccion_id=sf.sop_fraccion_id,
                    nivel_limpieza_id=nivel_id
                ).delete()

                still_has_any = (
                    db.session.query(SopFraccionDetalle.sop_fraccion_detalle_id)
                    .filter(SopFraccionDetalle.sop_fraccion_id == sf.sop_fraccion_id)
                    .first()
                    is not None
                )
                if not still_has_any:
                    db.session.delete(sf)

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
        flash(f"Fracciones guardadas para nivel {nivel}.", "success")
        return redirect(url_for("sop.sop_fracciones_edit", sop_id=sop.sop_id, nivel=nivel, tipo_sop=tipo_sop))

    return render_template(
        "sop/sop_crear.html",
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


# =========================
# SOP ELEMENTOSET EDIT
# =========================
@sop_bp.route("/sop/<sop_id>/elementoset", methods=["GET", "POST"])
@admin_required
def sop_elementoset_edit(sop_id):
    tipo_sop = (request.args.get("tipo_sop") or request.form.get("tipo_sop") or "regular").strip()
    if tipo_sop not in ("regular", "consecuente"):
        tipo_sop = "regular"

    nivel = (request.args.get("nivel") or request.form.get("nivel") or "").strip().lower()
    if nivel not in ("basica", "media", "profundo", "extraordinario"):
        nivel = "media"

    nivel_obj = NivelLimpieza.query.filter_by(nombre=nivel).first()
    if not nivel_obj:
        flash("Nivel de limpieza inválido.", "error")
        return redirect(url_for("sop.sop_panel"))

    nivel_id = int(nivel_obj.nivel_limpieza_id)

    sop = SOP.query.filter_by(sop_id=sop_id).first_or_404()
    subarea = sop.subarea

    sop_fraccion_id = (request.args.get("sop_fraccion_id") or request.form.get("sop_fraccion_id") or "").strip()
    if not sop_fraccion_id:
        flash("Falta sop_fraccion_id.", "warning")
        return redirect(url_for("sop.sop_detalles", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop))

    sf = SopFraccion.query.filter_by(sop_fraccion_id=sop_fraccion_id, sop_id=sop_id).first()
    if not sf:
        abort(404)

    fr = sf.fraccion

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

    es = None
    if detalle.elemento_set_id:
        es = ElementoSet.query.filter_by(elemento_set_id=detalle.elemento_set_id).first()

    if not es:
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
        detalle.kit_id = None
        detalle.receta_id = None
        detalle.consumo_id = None
        db.session.commit()

    elementos = (
        Elemento.query
        .filter_by(subarea_id=subarea.subarea_id)
        .order_by(Elemento.elemento_id.asc())
        .all()
    )

    detalles = (
        ElementoDetalle.query
        .filter_by(elemento_set_id=es.elemento_set_id)
        .all()
    )
    det_by_el = {d.elemento_id: d for d in (detalles or [])}

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

    if request.method == "POST":
        selected_ids = request.form.getlist("elemento_id")
        selected_set = set(selected_ids)

        for d in list(detalles or []):
            if str(d.elemento_id) not in selected_set:
                db.session.delete(d)

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
        flash("Elementos del set guardados.", "success")
        return redirect(url_for("sop.sop_elementoset_edit", sop_id=sop_id, nivel=nivel, tipo_sop=tipo_sop, sop_fraccion_id=sf.sop_fraccion_id))

    return render_template(
        "sop/sop_elementoset.html",
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


# ============================================================================
# SOP EVENTO - CREAR
# ============================================================================
@sop_bp.route('/sop-evento-crear', methods=['GET', 'POST'])
@admin_required
def sop_evento_crear():
    evento_tipo_id = request.args.get('evento_tipo_id') or request.form.get('evento_tipo_id')
    caso_id = request.args.get('caso_id') or request.form.get('caso_id')

    if not evento_tipo_id or not caso_id:
        flash('Debe seleccionar tipo de evento y caso', 'error')
        return redirect(url_for('sop.sop_panel'))

    evento = EventoCatalogo.query.get(evento_tipo_id)
    caso = CasoCatalogo.query.get(caso_id)

    if not evento or not caso:
        flash('Evento o caso no encontrado', 'error')
        return redirect(url_for('sop.sop_panel'))

    partes = caso_id.split('-')
    if len(partes) >= 3:
        tipo_corto = partes[1]
        caso_corto = partes[2]
    else:
        flash('Formato de caso_id inválido', 'error')
        return redirect(url_for('sop.sop_panel'))

    sop_evento_id = f"SP-{tipo_corto}-{caso_corto}-001"
    sop_evento = SopEvento.query.get(sop_evento_id)

    fracciones = (
        SopEventoFraccion.query
        .filter_by(evento_tipo_id=evento_tipo_id)
        .order_by(SopEventoFraccion.fraccion_evento_id.asc())
        .all()
    )

    selected_ids = set()
    orden_map = {}

    if sop_evento and sop_evento.detalles:
        selected_ids = {d.fraccion_evento_id for d in sop_evento.detalles}
        orden_map = {d.fraccion_evento_id: d.orden for d in sop_evento.detalles}

    if request.method == "POST":
        selected = request.form.getlist("fraccion_evento_id")
        selected_set = set(selected)

        if not selected:
            flash("Selecciona al menos 1 fracción", "warning")
            return redirect(url_for("sop.sop_evento_crear",
                                   evento_tipo_id=evento_tipo_id,
                                   caso_id=caso_id))

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

        prev_selected = selected_ids.copy() if selected_ids else set()
        to_remove = prev_selected - selected_set

        if to_remove:
            SopEventoDetalle.query.filter(
                SopEventoDetalle.sop_evento_id == sop_evento_id,
                SopEventoDetalle.fraccion_evento_id.in_(list(to_remove))
            ).delete(synchronize_session=False)

        for fraccion_id in selected:
            orden_raw = (request.form.get(f"orden_{fraccion_id}") or "").strip()
            orden = int(orden_raw) if orden_raw.isdigit() else 1000

            detalle = SopEventoDetalle.query.filter_by(
                sop_evento_id=sop_evento_id,
                fraccion_evento_id=fraccion_id
            ).first()

            if detalle:
                detalle.orden = orden
            else:
                nuevo_detalle = SopEventoDetalle(
                    sop_evento_id=sop_evento_id,
                    fraccion_evento_id=fraccion_id,
                    orden=orden,
                    tiempo_estimado=15
                )
                db.session.add(nuevo_detalle)

        db.session.commit()
        flash("Fracciones guardadas exitosamente", "success")

        return redirect(url_for("sop.sop_evento_editar",
                               sop_evento_id=sop_evento_id))

    return render_template(
        "sop/sop_evento_crear.html",
        sop_evento=sop_evento,
        sop_evento_id=sop_evento_id,
        evento=evento,
        caso=caso,
        fracciones=fracciones,
        selected_ids=selected_ids,
        orden_map=orden_map
    )


# ============================================================================
# SOP EVENTO - EDITAR
# ============================================================================
@sop_bp.route("/sop-evento/<sop_evento_id>/editar")
@admin_required
def sop_evento_editar(sop_evento_id):
    sop_evento = SopEvento.query.get_or_404(sop_evento_id)

    tiene_fracciones = (
        db.session.query(SopEventoDetalle.detalle_id)
        .filter_by(sop_evento_id=sop_evento_id)
        .first()
        is not None
    )

    if not tiene_fracciones:
        return redirect(url_for("sop.sop_evento_crear",
                               evento_tipo_id=sop_evento.evento_tipo_id,
                               caso_id=sop_evento.caso_id))

    primer_detalle = (
        SopEventoDetalle.query
        .filter_by(sop_evento_id=sop_evento_id)
        .order_by(SopEventoDetalle.orden.asc())
        .first()
    )

    return redirect(url_for("sop.sop_evento_detalle",
                           sop_evento_id=sop_evento_id,
                           detalle_id=primer_detalle.detalle_id))


# ============================================================================
# SOP EVENTO - DETALLE
# ============================================================================
@sop_bp.route("/sop-evento/<sop_evento_id>/detalle", methods=["GET", "POST"])
@admin_required
def sop_evento_detalle(sop_evento_id):
    sop_evento = SopEvento.query.get_or_404(sop_evento_id)

    if request.method == "POST":
        detalle_id = request.form.get("detalle_id", "").strip()

        if not detalle_id:
            flash("Detalle ID no encontrado", "error")
            return redirect(url_for("sop.sop_evento_detalle",
                                   sop_evento_id=sop_evento_id))

        detalle_actual = SopEventoDetalle.query.get(int(detalle_id))

        if not detalle_actual or detalle_actual.sop_evento_id != sop_evento_id:
            flash("Detalle no encontrado", "error")
            return redirect(url_for("sop.sop_evento_detalle",
                                   sop_evento_id=sop_evento_id))

        tiempo_raw = request.form.get("tiempo_estimado", "").strip()
        if tiempo_raw:
            try:
                detalle_actual.tiempo_estimado = int(tiempo_raw)
            except ValueError:
                flash("Tiempo inválido", "warning")
                return redirect(url_for("sop.sop_evento_detalle",
                                       sop_evento_id=sop_evento_id,
                                       detalle_id=detalle_actual.detalle_id))

        detalle_actual.kit_id = request.form.get("kit_id", "").strip() or None
        detalle_actual.receta_id = request.form.get("receta_id", "").strip() or None
        detalle_actual.consumo_id = request.form.get("consumo_id", "").strip() or None

        try:
            db.session.commit()
            flash("Detalle guardado", "success")
        except Exception as e:
            db.session.rollback()
            print("ERROR guardando detalle evento:", repr(e))
            flash("Error guardando detalle", "error")

        return redirect(url_for("sop.sop_evento_detalle",
                               sop_evento_id=sop_evento_id,
                               detalle_id=detalle_actual.detalle_id))

    detalles_list = (
        SopEventoDetalle.query
        .filter_by(sop_evento_id=sop_evento_id)
        .order_by(SopEventoDetalle.orden.asc())
        .all()
    )

    if not detalles_list:
        flash("Este SOP no tiene fracciones todavía", "warning")
        return redirect(url_for("sop.sop_panel",
                               evento_tipo_id=sop_evento.evento_tipo_id,
                               caso_id=sop_evento.caso_id))

    detalle_id = request.args.get("detalle_id", "").strip()

    if detalle_id:
        detalle_id = int(detalle_id)
        detalle_actual = next((d for d in detalles_list if d.detalle_id == detalle_id),
                             detalles_list[0])
    else:
        detalle_actual = detalles_list[0]

    kits = (
        Kit.query
        .filter_by(tipo_kit='evento', caso_id=sop_evento.caso_id)
        .order_by(Kit.nombre.asc())
        .all()
    )

    recetas = Receta.query.order_by(Receta.receta_id.asc()).all()
    consumos = Consumo.query.order_by(Consumo.consumo_id.asc()).all()

    metodologia = None
    if detalle_actual.fraccion.metodologia:
        metodologia = detalle_actual.fraccion.metodologia

    return render_template(
        "sop/sop_evento_detalle.html",
        sop_evento=sop_evento,
        detalles_list=detalles_list,
        detalle_actual=detalle_actual,
        kits=kits,
        recetas=recetas,
        consumos=consumos,
        metodologia=metodologia,
        hide_nav=True
    )
