# api_bp.py - Blueprint para APIs de catalogos y operaciones
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from ..models import (
    db, Area, SubArea, SOP, NivelLimpieza, Personal,
    Fraccion, Metodologia, MetodologiaBase, MetodologiaBasePaso,
    LanzamientoDia, LanzamientoTarea, TareaCheck,
    EventoCatalogo, CasoCatalogo, SopEventoFraccion,
    MetodologiaEventoFraccion, MetodologiaEventoFraccionPaso,
    SopEvento, SopEventoDetalle,
    Elemento, ElementoSet, ElementoDetalle,
    Kit, KitDetalle, Herramienta,
    Receta, RecetaDetalle, Quimico, Consumo,
    SopFraccion, SopFraccionDetalle,
)
from .helpers import admin_required, now_cdmx, today_cdmx

api_bp = Blueprint("api", __name__)


# =========================
# API - QUIMICOS (CRUD)
# =========================

@api_bp.route("/api/quimicos/catalogos", methods=["GET"])
@admin_required
def api_quimicos_catalogos():
    """Obtiene los catalogos dinamicos para crear/editar quimicos"""
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
        grupos = [
            {"codigo": codigo, "nombre": categoria}
            for codigo, categoria in sorted(GLOSARIO_QUIMICOS.items())
        ]
        presentaciones_raw = db.session.query(
            Quimico.presentacion
        ).filter(
            Quimico.presentacion.isnot(None),
            Quimico.presentacion != ''
        ).distinct().all()
        presentaciones = sorted([p[0] for p in presentaciones_raw if p[0]])
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


@api_bp.route("/api/quimicos/next-id", methods=["GET"])
@admin_required
def api_quimicos_next_id():
    """Genera el proximo ID disponible para un grupo especifico"""
    grupo = request.args.get("grupo", "").strip().upper()
    if not grupo:
        return jsonify({"success": False, "error": "Grupo requerido"}), 400
    if len(grupo) != 2:
        return jsonify({"success": False, "error": "Grupo debe tener 2 caracteres"}), 400
    try:
        pattern = f"QU-{grupo}-%"
        ultimo = Quimico.query.filter(
            Quimico.quimico_id.like(pattern)
        ).order_by(
            Quimico.quimico_id.desc()
        ).first()
        if ultimo:
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
            siguiente = 1
        nuevo_id = f"QU-{grupo}-{siguiente:03d}"
        return jsonify({
            "success": True,
            "quimico_id": nuevo_id,
            "grupo": grupo,
            "numero": siguiente
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/quimicos", methods=["POST"])
@admin_required
def api_quimicos_crear():
    """Crea un nuevo quimico"""
    try:
        data = request.get_json()
        grupo = data.get("grupo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        presentacion = data.get("presentacion", "").strip() or None
        unidad_base = data.get("unidad_base", "").strip() or None
        if not grupo or len(grupo) != 2:
            return jsonify({"success": False, "error": "Grupo invalido (2 caracteres)"}), 400
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        existe_nombre = Quimico.query.filter(
            db.func.upper(Quimico.nombre) == nombre.upper()
        ).first()
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe un quimico con el nombre '{nombre}'"
            }), 400
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
        categoria_ref = Quimico.query.filter(
            Quimico.quimico_id.like(pattern)
        ).first()
        if categoria_ref:
            categoria = categoria_ref.categoria
        else:
            categoria = grupo
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


@api_bp.route("/api/quimicos/<quimico_id>", methods=["PUT"])
@admin_required
def api_quimicos_editar(quimico_id):
    """Edita un quimico existente"""
    try:
        quimico = Quimico.query.get(quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Quimico no encontrado"}), 404
        data = request.get_json()
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_presentacion = data.get("presentacion", "").strip() or None
        nueva_unidad = data.get("unidad_base", "").strip() or None
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        existe_nombre = Quimico.query.filter(
            db.func.upper(Quimico.nombre) == nuevo_nombre.upper(),
            Quimico.quimico_id != quimico_id
        ).first()
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe otro quimico con el nombre '{nuevo_nombre}'"
            }), 400
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


@api_bp.route("/api/quimicos/<quimico_id>", methods=["DELETE"])
@admin_required
def api_quimicos_eliminar(quimico_id):
    """Elimina un quimico"""
    try:
        quimico = Quimico.query.get(quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Quimico no encontrado"}), 404
        en_recetas = RecetaDetalle.query.filter_by(quimico_id=quimico_id).count()
        if en_recetas > 0:
            recetas_nombres = db.session.query(Receta.nombre).join(
                RecetaDetalle
            ).filter(
                RecetaDetalle.quimico_id == quimico_id
            ).distinct().all()
            nombres = [r[0] for r in recetas_nombres]
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Este quimico esta en {en_recetas} receta(s)",
                "recetas": nombres
            }), 400
        db.session.delete(quimico)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Quimico {quimico_id} eliminado correctamente"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - RECETAS (CRUD)
# =========================

@api_bp.route("/api/recetas/catalogos", methods=["GET"])
@admin_required
def api_recetas_catalogos():
    """Obtiene los quimicos disponibles para crear/editar recetas"""
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


@api_bp.route("/api/recetas/next-id", methods=["GET"])
@admin_required
def api_recetas_next_id():
    """Genera el proximo ID disponible para un codigo especifico"""
    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jsonify({"success": False, "error": "Codigo requerido"}), 400
    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Codigo debe tener exactamente 2 caracteres"}), 400
    try:
        pattern = f"RE-{codigo}-%"
        ultima = Receta.query.filter(
            Receta.receta_id.like(pattern)
        ).order_by(
            Receta.receta_id.desc()
        ).first()
        if ultima:
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
            siguiente = 1
        nuevo_id = f"RE-{codigo}-{siguiente:03d}"
        return jsonify({
            "success": True,
            "receta_id": nuevo_id,
            "codigo": codigo,
            "numero": siguiente
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/recetas", methods=["POST"])
@admin_required
def api_recetas_crear():
    """Crea una nueva receta con su detalle"""
    try:
        data = request.get_json()
        codigo = data.get("codigo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        quimico_id = data.get("quimico_id", "").strip()
        dosis = data.get("dosis")
        volumen_base = data.get("volumen_base")
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo invalido"}), 400
        pattern_fraccion = f"FR-{codigo}-%"
        fraccion_existe = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern_fraccion)
        ).first()
        if not fraccion_existe:
            return jsonify({
                "success": False,
                "error": f"El codigo '{codigo}' no corresponde a ninguna fraccion existente"
            }), 400
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if not quimico_id:
            return jsonify({"success": False, "error": "Quimico requerido"}), 400
        if dosis is None or dosis < 0:
            return jsonify({"success": False, "error": "Dosis debe ser 0 o mayor"}), 400
        if volumen_base is None or volumen_base < 0:
            return jsonify({"success": False, "error": "Volumen base debe ser 0 o mayor"}), 400
        existe_nombre = Receta.query.filter(
            db.func.upper(Receta.nombre) == nombre.upper()
        ).first()
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe una receta con el nombre '{nombre}'"
            }), 400
        quimico = Quimico.query.get(quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Quimico no encontrado"}), 404
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
        nueva_receta = Receta(
            receta_id=receta_id,
            nombre=nombre
        )
        db.session.add(nueva_receta)
        db.session.flush()
        detalle = RecetaDetalle(
            receta_id=receta_id,
            quimico_id=quimico_id,
            dosis=dosis,
            unidad_dosis="mL",
            volumen_base=volumen_base,
            unidad_volumen="mL",
            nota=nombre
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


@api_bp.route("/api/recetas/<receta_id>", methods=["PUT"])
@admin_required
def api_recetas_editar(receta_id):
    """Edita una receta existente y su detalle"""
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
            return jsonify({"success": False, "error": "Quimico requerido"}), 400
        if nueva_dosis is None or nueva_dosis < 0:
            return jsonify({"success": False, "error": "Dosis debe ser 0 o mayor"}), 400
        if nuevo_volumen is None or nuevo_volumen < 0:
            return jsonify({"success": False, "error": "Volumen base debe ser 0 o mayor"}), 400
        existe_nombre = Receta.query.filter(
            db.func.upper(Receta.nombre) == nuevo_nombre.upper(),
            Receta.receta_id != receta_id
        ).first()
        if existe_nombre:
            return jsonify({
                "success": False,
                "error": f"Ya existe otra receta con el nombre '{nuevo_nombre}'"
            }), 400
        quimico = Quimico.query.get(nuevo_quimico_id)
        if not quimico:
            return jsonify({"success": False, "error": "Quimico no encontrado"}), 404
        receta.nombre = nuevo_nombre
        detalle = RecetaDetalle.query.filter_by(receta_id=receta_id).first()
        if detalle:
            detalle.quimico_id = nuevo_quimico_id
            detalle.dosis = nueva_dosis
            detalle.volumen_base = nuevo_volumen
            detalle.nota = nuevo_nombre
        else:
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


@api_bp.route("/api/recetas/<receta_id>", methods=["DELETE"])
@admin_required
def api_recetas_eliminar(receta_id):
    """Elimina una receta y su detalle"""
    try:
        receta = Receta.query.get(receta_id)
        if not receta:
            return jsonify({"success": False, "error": "Receta no encontrada"}), 404
        en_eventos = db.session.query(SopEventoDetalle).filter_by(receta_id=receta_id).count()
        en_elementos = db.session.query(ElementoDetalle).filter_by(receta_id=receta_id).count()
        en_fracciones = db.session.query(SopFraccionDetalle).filter_by(receta_id=receta_id).count()
        total_usos = en_eventos + en_elementos + en_fracciones
        if total_usos > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta receta esta en uso en {total_usos} lugar(es)",
                "detalles": {
                    "eventos": en_eventos,
                    "elementos": en_elementos,
                    "fracciones": en_fracciones
                }
            }), 400
        RecetaDetalle.query.filter_by(receta_id=receta_id).delete()
        db.session.delete(receta)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Receta {receta_id} eliminada correctamente"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/recetas/fracciones-disponibles", methods=["GET"])
@admin_required
def api_recetas_fracciones_disponibles():
    """Retorna fracciones disponibles para crear recetas"""
    try:
        fracciones = Fraccion.query.order_by(Fraccion.fraccion_id).all()
        fracciones_data = []
        for f in fracciones:
            partes = f.fraccion_id.split('-')
            codigo = partes[1] if len(partes) >= 2 else ''
            nombre_full = f.fraccion_nombre
            if f.nombre_custom:
                nombre_full = f"{f.fraccion_nombre} - {f.nombre_custom}"
            fracciones_data.append({
                "fraccion_id": f.fraccion_id,
                "codigo": codigo,
                "nombre": f.fraccion_nombre,
                "nombre_custom": f.nombre_custom,
                "nombre_full": nombre_full
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

@api_bp.route("/api/consumos/next-id", methods=["GET"])
@admin_required
def api_consumos_next_id():
    """Genera el proximo ID disponible para consumos"""
    try:
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


@api_bp.route("/api/consumos", methods=["POST"])
@admin_required
def api_consumos_crear():
    """Crea un nuevo consumo"""
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


@api_bp.route("/api/consumos/<consumo_id>", methods=["PUT"])
@admin_required
def api_consumos_editar(consumo_id):
    """Edita un consumo existente"""
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


@api_bp.route("/api/consumos/<consumo_id>", methods=["DELETE"])
@admin_required
def api_consumos_eliminar(consumo_id):
    """Elimina un consumo"""
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
                "error": f"No se puede eliminar. Este consumo esta en uso en {total_usos} lugar(es)",
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


# =========================
# API - ELEMENTOS (CRUD)
# =========================

@api_bp.route('/api/elementos/catalogos', methods=['GET'])
def api_elementos_catalogos():
    """Obtener datos para poblar dropdowns de elementos"""
    try:
        # Lista completa de nombres disponibles en el sistema
        NOMBRES_DISPONIBLES = [
            'A/C', 'ACCESO', 'ACCESORIO', 'ARCHIVERO', 'BANCO', 'BANQUILLO', 
            'BASCULA', 'BASE', 'BORDE', 'CAMILLA', 'CESTO', 'CHAPA', 'CUADRO', 
            'DETECTOR', 'ESCRITORIO', 'ESPEJO', 'EXTINTOR', 'GABINETE', 'LAMPARA', 
            'LAVABO', 'LIBRERO', 'LUZ', 'MESA', 'MICROONDAS', 'MUEBLE', 'PARED', 
            'PERCHERO', 'PROYECCION', 'PROYECTOR', 'PUERTA', 'REFRIGERADOR', 
            'SANITARIO', 'SENALETICA', 'SILLA', 'SOFA', 'TELEVISION', 'TUBERIA', 
            'VIGA', 'REPISA', 'LOCKER', 'BARANDAL',
        ]
        
        areas = Area.query.order_by(Area.orden_area).all()
        areas_data = [
            {'area_id': a.area_id, 'nombre': a.area_nombre}
            for a in areas
        ]
        
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
        
        # Usar la lista predefinida (ya está ordenada alfabéticamente)
        grupos_data = sorted(NOMBRES_DISPONIBLES)
        
        descripciones_query = db.session.query(
            Elemento.nombre, Elemento.descripcion
        ).distinct().order_by(Elemento.nombre, Elemento.descripcion).all()
        
        descripciones_por_grupo = {}
        for nombre, descripcion in descripciones_query:
            if nombre not in descripciones_por_grupo:
                descripciones_por_grupo[nombre] = []
            if descripcion:
                descripciones_por_grupo[nombre].append(descripcion)
        
        return jsonify({
            'areas': areas_data,
            'subareas': subareas_data,
            'grupos': grupos_data,
            'descripciones_por_grupo': descripciones_por_grupo
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/api/elementos', methods=['GET'])
def api_elementos_list():
    """Lista elementos con paginacion y filtros"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        area_id = request.args.get('area_id')
        subarea_id = request.args.get('subarea_id')
        query = Elemento.query.join(SubArea).join(Area)
        if subarea_id:
            query = query.filter(Elemento.subarea_id == subarea_id)
        elif area_id:
            query = query.filter(SubArea.area_id == area_id)
        query = query.order_by(Elemento.elemento_id)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
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


@api_bp.route('/api/elementos/next-id', methods=['GET'])
def api_elementos_next_id():
    """Genera el proximo ID para un elemento"""
    try:
        CODIGOS_ELEMENTO = {
            'A/C': 'AR', 'ACCESO': 'AE', 'ACCESORIO': 'AC', 'ARCHIVERO': 'AH',
            'BANCO': 'BA', 'BANQUILLO': 'BN', 'BASCULA': 'BC', 'BASE': 'BS',
            'BORDE': ['BO', 'BP'], 'CAMILLA': 'CA', 'CESTO': 'CE', 'CHAPA': 'CH',
            'CUADRO': 'CU', 'DETECTOR': 'DE', 'ESCRITORIO': 'EC', 'ESPEJO': 'ES',
            'EXTINTOR': 'EX', 'GABINETE': 'GE', 'LAMPARA': 'LM', 'LAVABO': 'LA',
            'LIBRERO': 'LI', 'LUZ': 'LZ', 'MESA': 'ME', 'MICROONDAS': 'MI',
            'MUEBLE': 'MU', 'PARED': 'PR', 'PERCHERO': 'PE', 'PROYECCION': 'PO',
            'PROYECTOR': 'PY', 'PUERTA': 'PU', 'REFRIGERADOR': 'RE', 'SANITARIO': 'SA',
            'SENALETICA': 'SE', 'SILLA': 'SI', 'SOFA': 'SO', 'TELEVISION': 'TV',
            'TUBERIA': 'TU', 'VIGA': 'VG', 'REPISA': 'RP', 'LOCKER': 'LO', 'BARANDAL': 'BR',
        }
        nombre = request.args.get('nombre')
        descripcion = request.args.get('descripcion')
        if not nombre or not descripcion:
            return jsonify({'error': 'Faltan parametros: nombre y descripcion'}), 400
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
        next_id = f'EL-{codigo}-{siguiente_num:03d}'
        return jsonify({'next_id': next_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/api/elementos', methods=['POST'])
def api_elementos_create():
    """Crea un nuevo elemento"""
    try:
        CODIGOS_ELEMENTO = {
            'A/C': 'AR', 'ACCESO': 'AE', 'ACCESORIO': 'AC', 'ARCHIVERO': 'AH',
            'BANCO': 'BA', 'BANQUILLO': 'BN', 'BASCULA': 'BC', 'BASE': 'BS',
            'BORDE': ['BO', 'BP'], 'CAMILLA': 'CA', 'CESTO': 'CE', 'CHAPA': 'CH',
            'CUADRO': 'CU', 'DETECTOR': 'DE', 'ESCRITORIO': 'EC', 'ESPEJO': 'ES',
            'EXTINTOR': 'EX', 'GABINETE': 'GE', 'LAMPARA': 'LM', 'LAVABO': 'LA',
            'LIBRERO': 'LI', 'LUZ': 'LZ', 'MESA': 'ME', 'MICROONDAS': 'MI',
            'MUEBLE': 'MU', 'PARED': 'PR', 'PERCHERO': 'PE', 'PROYECCION': 'PO',
            'PROYECTOR': 'PY', 'PUERTA': 'PU', 'REFRIGERADOR': 'RE', 'SANITARIO': 'SA',
            'SENALETICA': 'SE', 'SILLA': 'SI', 'SOFA': 'SO', 'TELEVISION': 'TV',
            'TUBERIA': 'TU', 'VIGA': 'VG', 'REPISA': 'RP', 'LOCKER': 'LO', 'BARANDAL': 'BR',
        }
        data = request.get_json()
        required_fields = ['subarea_id', 'nombre', 'descripcion', 'cantidad']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo requerido: {field}'}), 400
        cantidad = data['cantidad']
        if not isinstance(cantidad, (int, float)) or cantidad < 1:
            return jsonify({'error': 'La cantidad debe ser un numero mayor o igual a 1'}), 400
        subarea = SubArea.query.get(data['subarea_id'])
        if not subarea:
            return jsonify({'error': 'SubArea no encontrada'}), 404
        nombre = data['nombre'].upper()
        descripcion = data['descripcion']
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
        nuevo_elemento = Elemento(
            elemento_id=elemento_id,
            subarea_id=data['subarea_id'],
            nombre=nombre,
            descripcion=data['descripcion'],
            cantidad=cantidad,
            estatus='ACTIVO'
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
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Error de integridad: posiblemente el elemento ya existe'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/api/elementos/<elemento_id>', methods=['PUT'])
def api_elementos_update(elemento_id):
    """Edita un elemento existente"""
    try:
        data = request.get_json()
        elemento = Elemento.query.get(elemento_id)
        if not elemento:
            return jsonify({'error': 'Elemento no encontrado'}), 404
        allowed_fields = ['cantidad', 'estatus']
        for field in data.keys():
            if field not in allowed_fields:
                return jsonify({'error': f'Campo no editable: {field}'}), 400
        if 'cantidad' in data:
            cantidad = data['cantidad']
            if not isinstance(cantidad, (int, float)) or cantidad < 1:
                return jsonify({'error': 'La cantidad debe ser un numero mayor o igual a 1'}), 400
            elemento.cantidad = cantidad
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


@api_bp.route('/api/elementos/<elemento_id>', methods=['DELETE'])
def api_elementos_delete(elemento_id):
    """Elimina un elemento"""
    try:
        elemento = Elemento.query.get(elemento_id)
        if not elemento:
            return jsonify({'error': 'Elemento no encontrado'}), 404
        en_uso = ElementoDetalle.query.filter_by(elemento_id=elemento_id).first()
        if en_uso:
            return jsonify({
                'error': 'No se puede eliminar el elemento porque esta en uso en ElementoDetalle'
            }), 400
        db.session.delete(elemento)
        db.session.commit()
        return jsonify({'message': 'Elemento eliminado exitosamente'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# =========================
# API - HERRAMIENTAS (CRUD)
# =========================

@api_bp.route("/api/herramientas/catalogos", methods=["GET"])
@admin_required
def api_herramientas_catalogos():
    """Obtiene el glosario fijo de grupos de herramientas"""
    try:
        GLOSARIO_HERRAMIENTAS = {
            'AT': 'ATOMIZADOR', 'BA': 'BASTON', 'BL': 'BOLSA', 'BS': 'BASE',
            'CA': 'CARRITO', 'CE': 'CEPILLO', 'CU': 'CUBETA', 'EO': 'ESPONJA',
            'EP': 'ESPATULA', 'ES': 'ESCOBA', 'EX': 'EXPRIMIDOR', 'FI': 'FIBRA',
            'GU': 'GUANTES', 'JA': 'JALADOR', 'MA': 'MANGUERA', 'MO': 'MOP',
            'OR': 'ORGANIZADOR', 'PA': 'PANO', 'PL': 'PLUMERO', 'RE': 'RECOGEDOR',
            'SE': 'SENALETICA', 'TO': 'TOALLAS', 'TP': 'TOPE', 'TR': 'TRAPEADOR',
        }
        grupos = [
            {"codigo": codigo, "nombre": nombre}
            for codigo, nombre in sorted(GLOSARIO_HERRAMIENTAS.items())
        ]
        return jsonify({"success": True, "grupos": grupos})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/herramientas/next-id", methods=["GET"])
@admin_required
def api_herramientas_next_id():
    """Genera el proximo ID disponible para un grupo"""
    grupo = request.args.get("grupo", "").strip().upper()
    if not grupo:
        return jsonify({"success": False, "error": "Grupo requerido"}), 400
    if len(grupo) != 2:
        return jsonify({"success": False, "error": "Grupo debe tener 2 caracteres"}), 400
    try:
        pattern = f"HE-{grupo}-%"
        ultima = Herramienta.query.filter(
            Herramienta.herramienta_id.like(pattern)
        ).order_by(Herramienta.herramienta_id.desc()).first()
        if ultima:
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
            siguiente = 1
        nuevo_id = f"HE-{grupo}-{siguiente:03d}"
        return jsonify({
            "success": True,
            "herramienta_id": nuevo_id,
            "grupo": grupo,
            "numero": siguiente
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/herramientas", methods=["GET"])
@admin_required
def api_herramientas_listar():
    """Lista todas las herramientas con paginacion y filtros"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        grupo = request.args.get('grupo', '').strip().upper()
        estatus = request.args.get('estatus', '').strip()
        query = Herramienta.query
        if grupo:
            pattern = f"HE-{grupo}-%"
            query = query.filter(Herramienta.herramienta_id.like(pattern))
        if estatus:
            query = query.filter(Herramienta.estatus == estatus)
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


@api_bp.route("/api/herramientas", methods=["POST"])
@admin_required
def api_herramientas_crear():
    """Crea una nueva herramienta"""
    try:
        GLOSARIO_HERRAMIENTAS = {
            'AT': 'ATOMIZADOR', 'BA': 'BASTON', 'BL': 'BOLSA', 'BS': 'BASE',
            'CA': 'CARRITO', 'CE': 'CEPILLO', 'CU': 'CUBETA', 'EO': 'ESPONJA',
            'EP': 'ESPATULA', 'ES': 'ESCOBA', 'EX': 'EXPRIMIDOR', 'FI': 'FIBRA',
            'GU': 'GUANTES', 'JA': 'JALADOR', 'MA': 'MANGUERA', 'MO': 'MOP',
            'OR': 'ORGANIZADOR', 'PA': 'PANO', 'PL': 'PLUMERO', 'RE': 'RECOGEDOR',
            'SE': 'SENALETICA', 'TO': 'TOALLAS', 'TP': 'TOPE', 'TR': 'TRAPEADOR',
        }
        data = request.get_json()
        grupo = data.get("grupo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        descripcion = data.get("descripcion", "").strip()
        if not grupo or len(grupo) != 2:
            return jsonify({"success": False, "error": "Grupo invalido (2 caracteres)"}), 400
        if grupo not in GLOSARIO_HERRAMIENTAS:
            return jsonify({
                "success": False,
                "error": f"Grupo '{grupo}' no valido"
            }), 400
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if not descripcion:
            descripcion = nombre
        pattern = f"HE-{grupo}-%"
        ultima = Herramienta.query.filter(
            Herramienta.herramienta_id.like(pattern)
        ).order_by(Herramienta.herramienta_id.desc()).first()
        if ultima:
            partes = ultima.herramienta_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        herramienta_id = f"HE-{grupo}-{siguiente:03d}"
        nueva_herramienta = Herramienta(
            herramienta_id=herramienta_id,
            nombre=nombre,
            descripcion=descripcion,
            estatus='Activo'
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


@api_bp.route("/api/herramientas/<herramienta_id>", methods=["PUT"])
@admin_required
def api_herramientas_editar(herramienta_id):
    """Edita una herramienta existente"""
    try:
        herramienta = Herramienta.query.get(herramienta_id)
        if not herramienta:
            return jsonify({"success": False, "error": "Herramienta no encontrada"}), 404
        data = request.get_json()
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_descripcion = data.get("descripcion", "").strip()
        nuevo_estatus = data.get("estatus", "").strip()
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if not nueva_descripcion:
            return jsonify({"success": False, "error": "Descripcion requerida"}), 400
        if nuevo_estatus not in ['Activo', 'Inactivo']:
            return jsonify({"success": False, "error": "Estatus debe ser 'Activo' o 'Inactivo'"}), 400
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


@api_bp.route("/api/herramientas/<herramienta_id>", methods=["DELETE"])
@admin_required
def api_herramientas_eliminar(herramienta_id):
    """Elimina una herramienta"""
    try:
        herramienta = Herramienta.query.get(herramienta_id)
        if not herramienta:
            return jsonify({"success": False, "error": "Herramienta no encontrada"}), 404
        en_kits = KitDetalle.query.filter_by(herramienta_id=herramienta_id).count()
        if en_kits > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta herramienta esta en {en_kits} kit(s)"
            }), 400
        db.session.delete(herramienta)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Herramienta {herramienta_id} eliminada correctamente"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - KITS (CRUD)
# =========================

@api_bp.route("/api/kits/fracciones-disponibles", methods=["GET"])
@admin_required
def api_kits_fracciones_disponibles():
    """Retorna fracciones disponibles para crear kits"""
    try:
        fracciones = Fraccion.query.order_by(Fraccion.fraccion_id).all()
        fracciones_data = []
        for f in fracciones:
            partes = f.fraccion_id.split('-')
            codigo = partes[1] if len(partes) >= 2 else ''
            nombre_full = f.fraccion_nombre
            if f.nombre_custom:
                nombre_full = f"{f.fraccion_nombre} - {f.nombre_custom}"
            fracciones_data.append({
                "fraccion_id": f.fraccion_id,
                "codigo": codigo,
                "nombre": f.fraccion_nombre,
                "nombre_custom": f.nombre_custom,
                "nombre_full": nombre_full
            })
        return jsonify({"success": True, "fracciones": fracciones_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kits/herramientas-disponibles", methods=["GET"])
@admin_required
def api_kits_herramientas_disponibles():
    """Lista herramientas activas para checkboxes"""
    try:
        grupo = request.args.get('grupo', '').strip().upper()
        query = Herramienta.query.filter_by(estatus='Activo')
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


@api_bp.route("/api/kits/next-id", methods=["GET"])
@admin_required
def api_kits_next_id():
    """Genera el proximo ID disponible para un codigo de fraccion"""
    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jsonify({"success": False, "error": "Codigo requerido"}), 400
    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
    try:
        pattern = f"KT-{codigo}-%"
        ultimo = Kit.query.filter(Kit.kit_id.like(pattern)).order_by(Kit.kit_id.desc()).first()
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


@api_bp.route("/api/kits", methods=["GET"])
@admin_required
def api_kits_listar():
    """Lista todos los kits con sus herramientas"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        fraccion = request.args.get('fraccion', '').strip().upper()
        nivel = request.args.get('nivel', '').strip()
        tipo_kit = request.args.get('tipo_kit', '').strip()
        query = Kit.query
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
        query = query.order_by(Kit.kit_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        kits_data = []
        for k in pagination.items:
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


@api_bp.route("/api/kits", methods=["POST"])
@admin_required
def api_kits_crear():
    """Crea un nuevo kit con sus herramientas"""
    try:
        data = request.get_json()
        codigo = data.get("codigo", "").strip().upper()
        fraccion_id = data.get("fraccion_id", "").strip()
        nombre = data.get("nombre", "").strip()
        nivel_limpieza_id = data.get("nivel_limpieza_id")
        herramientas_ids = data.get("herramientas", [])
        if not codigo or not fraccion_id:
            return jsonify({"success": False, "error": "Codigo y fraccion requeridos"}), 400
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": f"Fraccion {fraccion_id} no encontrada"}), 404
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if nivel_limpieza_id is not None:
            if nivel_limpieza_id not in [1, 2, 3, 4]:
                return jsonify({"success": False, "error": "Nivel debe ser 1, 2, 3, 4 o null"}), 400
        if not herramientas_ids or len(herramientas_ids) == 0:
            return jsonify({"success": False, "error": "Debe seleccionar al menos 1 herramienta"}), 400
        for h_id in herramientas_ids:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        pattern = f"KT-{codigo}-%"
        ultimo = Kit.query.filter(Kit.kit_id.like(pattern)).order_by(Kit.kit_id.desc()).first()
        if ultimo:
            partes = ultimo.kit_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        kit_id = f"KT-{codigo}-{siguiente:03d}"
        nuevo_kit = Kit(
            kit_id=kit_id,
            fraccion_id=fraccion_id,
            nivel_limpieza_id=nivel_limpieza_id,
            nombre=nombre,
            tipo_kit='sop',
            caso_id=None
        )
        db.session.add(nuevo_kit)
        db.session.flush()
        for h_id in herramientas_ids:
            detalle = KitDetalle(kit_id=kit_id, herramienta_id=h_id, nota=nombre)
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


@api_bp.route("/api/kits/<kit_id>", methods=["PUT"])
@admin_required
def api_kits_editar(kit_id):
    """Edita un kit existente"""
    try:
        kit = Kit.query.get(kit_id)
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        data = request.get_json()
        nuevo_nombre = data.get("nombre", "").strip()
        nuevo_nivel = data.get("nivel_limpieza_id")
        nuevas_herramientas = data.get("herramientas", [])
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if nuevo_nivel is not None:
            if nuevo_nivel not in [1, 2, 3, 4]:
                return jsonify({"success": False, "error": "Nivel debe ser 1, 2, 3, 4 o null"}), 400
        if not nuevas_herramientas or len(nuevas_herramientas) == 0:
            return jsonify({"success": False, "error": "Debe tener al menos 1 herramienta"}), 400
        for h_id in nuevas_herramientas:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        kit.nombre = nuevo_nombre
        kit.nivel_limpieza_id = nuevo_nivel
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        for h_id in nuevas_herramientas:
            detalle = KitDetalle(kit_id=kit_id, herramienta_id=h_id, nota=nuevo_nombre)
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


@api_bp.route("/api/kits/<kit_id>", methods=["DELETE"])
@admin_required
def api_kits_eliminar(kit_id):
    """Elimina un kit y sus herramientas"""
    try:
        kit = Kit.query.get(kit_id)
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        db.session.delete(kit)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Kit {kit_id} eliminado correctamente"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# ======================================================
# API: Marcar/Desmarcar tarea (Operativo)
# ======================================================
@api_bp.route("/api/tarea/<int:tarea_id>/check", methods=["POST"])
@login_required
def marcar_tarea_check(tarea_id):
    """Marca una tarea como completada"""
    if current_user.role == "admin":
        return {"error": "Admin no puede marcar tareas"}, 403

    tarea = LanzamientoTarea.query.get_or_404(tarea_id)

    if tarea.personal_id != current_user.personal_id:
        return {"error": "Esta tarea no te pertenece"}, 403

    hoy = today_cdmx()
    dia = LanzamientoDia.query.get(tarea.dia_id)
    if not dia or dia.fecha != hoy:
        return {"error": "Solo puedes marcar tareas de hoy"}, 403

    existing = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
    if existing:
        return {
            "error": "Tarea ya marcada",
            "checked_at": existing.checked_at.strftime("%H:%M")
        }, 400

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


@api_bp.route("/api/tarea/<int:tarea_id>/check", methods=["DELETE"])
@login_required
def desmarcar_tarea_check(tarea_id):
    """Desmarca una tarea completada"""
    if current_user.role == "admin":
        return {"error": "Admin no puede desmarcar tareas"}, 403

    tarea = LanzamientoTarea.query.get_or_404(tarea_id)

    if tarea.personal_id != current_user.personal_id:
        return {"error": "Esta tarea no te pertenece"}, 403

    hoy = today_cdmx()
    dia = LanzamientoDia.query.get(tarea.dia_id)
    if not dia or dia.fecha != hoy:
        return {"error": "Solo puedes modificar tareas de hoy"}, 403

    check = TareaCheck.query.filter_by(tarea_id=tarea_id).first()
    if not check:
        return {"error": "Tarea no estaba marcada"}, 404

    db.session.delete(check)
    db.session.commit()

    return {"success": True}, 200


# ======================================================
# API: Verificar SOP existe
# ======================================================
@api_bp.route("/api/verificar_sop/<subarea_id>/<tipo_sop>")
@admin_required
def verificar_sop_existe(subarea_id, tipo_sop):
    """Verifica si existe un SOP del tipo especificado"""
    if tipo_sop not in ("regular", "consecuente"):
        return jsonify({"existe": False, "sop_id": None, "error": "Tipo SOP invalido"})

    sop = SOP.query.filter_by(subarea_id=subarea_id, tipo_sop=tipo_sop).first()

    return jsonify({
        "existe": sop is not None,
        "sop_id": sop.sop_id if sop else None
    })


@api_bp.route("/api/subareas_con_sop/<area_id>")
@admin_required
def subareas_con_sop(area_id):
    """Retorna subareas con informacion de SOPs disponibles"""
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


# =========================
# API - FRACCIONES (CRUD)
# =========================

@api_bp.route("/api/fracciones/catalogos", methods=["GET"])
@admin_required
def api_fracciones_catalogos():
    """Obtiene el glosario de fracciones para dropdown"""
    try:
        GLOSARIO_FRACCIONES = {
            'SE': 'Colocar Senaletica',
            'BS': 'Sacar Basura',
            'SP': 'Sacudir Superficies',
            'VI': 'Limpiar Vidrios',
            'BA': 'Barrer',
            'TL': 'Tallar Bano',
            'CN': 'Reabastecer Consumibles',
            'SA': 'Sacudir Elementos',
            'TA': 'Lavar Trastes',
            'AC': 'Acomodar Trastes',
            'MS': 'Mop Seco',
            'MH': 'Mop Humedo',
            'TR': 'Trapear',
        }
        grupos = [
            {"codigo": codigo, "nombre": nombre}
            for codigo, nombre in sorted(GLOSARIO_FRACCIONES.items())
        ]
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


@api_bp.route("/api/fracciones/next-id", methods=["GET"])
@admin_required
def api_fracciones_next_id():
    """Genera el proximo ID disponible para un codigo especifico"""
    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jsonify({"success": False, "error": "Codigo requerido"}), 400
    if len(codigo) != 2:
        return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
    try:
        pattern = f"FR-{codigo}-%"
        ultima = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern)
        ).order_by(Fraccion.fraccion_id.desc()).first()
        if ultima:
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
            siguiente = 1
        nuevo_id = f"FR-{codigo}-{siguiente:03d}"
        es_primera = (siguiente == 1)
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
            "es_primera": es_primera,
            "customs_existentes": customs_existentes
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/fracciones", methods=["GET"])
@admin_required
def api_fracciones_listar():
    """Lista todas las fracciones con paginacion y filtros"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        grupo = request.args.get('grupo', '').strip()
        query = Fraccion.query
        if grupo:
            query = query.filter(Fraccion.grupo_fracciones == grupo)
        query = query.order_by(Fraccion.fraccion_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        fracciones_data = []
        for f in pagination.items:
            niveles = db.session.query(Metodologia.nivel_limpieza_id)\
                .filter_by(fraccion_id=f.fraccion_id)\
                .order_by(Metodologia.nivel_limpieza_id)\
                .all()
            niveles_ids = [n[0] for n in niveles]
            nivel_map = {1: 'B', 2: 'M', 3: 'P', 4: 'E'}
            niveles_letras = [nivel_map.get(n, str(n)) for n in niveles_ids]
            fracciones_data.append({
                'fraccion_id': f.fraccion_id,
                'fraccion_nombre': f.fraccion_nombre,
                'nombre_custom': f.nombre_custom,
                'nota_tecnica': f.nota_tecnica,
                'grupo_fracciones': f.grupo_fracciones,
                'codigo': f.fraccion_id.split('-')[1] if '-' in f.fraccion_id else '',
                'niveles': niveles_ids,
                'niveles_display': ' '.join(niveles_letras)
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


@api_bp.route("/api/fracciones", methods=["POST"])
@admin_required
def api_fracciones_crear():
    """Crea una nueva fraccion"""
    try:
        GLOSARIO_FRACCIONES = {
            'SE': 'Colocar Senaletica',
            'BS': 'Sacar Basura',
            'SP': 'Sacudir Superficies',
            'VI': 'Limpiar Vidrios',
            'BA': 'Barrer',
            'TL': 'Tallar Bano',
            'CN': 'Reabastecer Consumibles',
            'SA': 'Sacudir Elementos',
            'TA': 'Lavar Trastes',
            'AC': 'Acomodar Trastes',
            'MS': 'Mop Seco',
            'MH': 'Mop Humedo',
            'TR': 'Trapear',
        }
        data = request.get_json()
        codigo = data.get("codigo", "").strip().upper()
        nombre_custom = data.get("nombre_custom", "").strip() or None
        nota_tecnica = data.get("nota_tecnica", "").strip() or None
        grupo_fracciones = data.get("grupo_fracciones", "").strip() or None
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo invalido (2 caracteres)"}), 400
        if codigo not in GLOSARIO_FRACCIONES:
            return jsonify({
                "success": False,
                "error": f"Codigo '{codigo}' no valido"
            }), 400
        nombre_base = GLOSARIO_FRACCIONES[codigo]
        if grupo_fracciones and grupo_fracciones not in ['administracion', 'produccion']:
            return jsonify({"success": False, "error": "Grupo debe ser 'administracion' o 'produccion'"}), 400
        pattern = f"FR-{codigo}-%"
        ultima = Fraccion.query.filter(
            Fraccion.fraccion_id.like(pattern)
        ).order_by(Fraccion.fraccion_id.desc()).first()
        if ultima:
            partes = ultima.fraccion_id.split('-')
            numero_actual = int(partes[2]) if len(partes) == 3 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        fraccion_id = f"FR-{codigo}-{siguiente:03d}"
        es_primera = (siguiente == 1)
        if es_primera:
            if nombre_custom:
                return jsonify({
                    "success": False,
                    "error": "La primera fraccion no debe tener nombre custom"
                }), 400
        else:
            if not nombre_custom:
                return jsonify({
                    "success": False,
                    "error": f"Este codigo ya existe. Debes agregar un nombre custom"
                }), 400
            if nombre_custom.upper() == nombre_base.upper():
                return jsonify({
                    "success": False,
                    "error": "El nombre custom no puede ser igual al nombre base"
                }), 400
            custom_duplicado = Fraccion.query.filter(
                Fraccion.fraccion_id.like(pattern),
                db.func.upper(Fraccion.nombre_custom) == nombre_custom.upper()
            ).first()
            if custom_duplicado:
                return jsonify({
                    "success": False,
                    "error": f"Ya existe otra fraccion con el custom '{nombre_custom}'"
                }), 400
        nueva_fraccion = Fraccion(
            fraccion_id=fraccion_id,
            fraccion_nombre=nombre_base,
            nombre_custom=nombre_custom,
            nota_tecnica=nota_tecnica,
            grupo_fracciones=grupo_fracciones
        )
        db.session.add(nueva_fraccion)
        db.session.commit()
        nombre_full = nombre_base
        if nombre_custom:
            nombre_full = f"{nombre_base} - {nombre_custom}"
        return jsonify({
            "success": True,
            "fraccion": {
                "fraccion_id": nueva_fraccion.fraccion_id,
                "fraccion_nombre": nueva_fraccion.fraccion_nombre,
                "nombre_custom": nueva_fraccion.nombre_custom,
                "nombre_full": nombre_full,
                "nota_tecnica": nueva_fraccion.nota_tecnica,
                "grupo_fracciones": nueva_fraccion.grupo_fracciones,
                "es_primera": es_primera
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/fracciones/<fraccion_id>", methods=["PUT"])
@admin_required
def api_fracciones_editar(fraccion_id):
    """Edita una fraccion existente"""
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        data = request.get_json()
        nuevo_custom = data.get("nombre_custom", "").strip() or None
        nueva_nota = data.get("nota_tecnica", "").strip() or None
        nuevo_grupo = data.get("grupo_fracciones", "").strip() or None
        if nuevo_grupo and nuevo_grupo not in ['administracion', 'produccion']:
            return jsonify({"success": False, "error": "Grupo debe ser 'administracion' o 'produccion'"}), 400
        fraccion.nombre_custom = nuevo_custom
        fraccion.nota_tecnica = nueva_nota
        fraccion.grupo_fracciones = nuevo_grupo
        db.session.commit()
        nombre_full = fraccion.fraccion_nombre
        if nuevo_custom:
            nombre_full = f"{fraccion.fraccion_nombre} - {nuevo_custom}"
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


@api_bp.route("/api/fracciones/<fraccion_id>", methods=["DELETE"])
@admin_required
def api_fracciones_eliminar(fraccion_id):
    """Elimina una fraccion"""
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        sops_count = db.session.query(SopFraccion).filter_by(fraccion_id=fraccion_id).count()
        elemento_sets_count = db.session.query(ElementoSet).filter_by(fraccion_id=fraccion_id).count()
        kits_count = db.session.query(Kit).filter(Kit.fraccion_id == fraccion_id).count()
        if sops_count > 0 or elemento_sets_count > 0 or kits_count > 0:
            return jsonify({
                "success": False,
                "error": "No se puede eliminar. La fraccion esta en uso.",
                "detalles": {
                    "sops": sops_count,
                    "elemento_sets": elemento_sets_count,
                    "kits": kits_count
                }
            }), 400
        metodologias = Metodologia.query.filter_by(fraccion_id=fraccion_id).all()
        metodologias_borradas = []
        for met in metodologias:
            metodologia_base_id = met.metodologia_base_id
            otras_fracciones = Metodologia.query.filter(
                Metodologia.metodologia_base_id == metodologia_base_id,
                Metodologia.fraccion_id != fraccion_id
            ).count()
            if otras_fracciones > 0:
                db.session.delete(met)
            else:
                MetodologiaBasePaso.query.filter_by(
                    metodologia_base_id=metodologia_base_id
                ).delete()
                db.session.delete(met)
                metodologia_base = MetodologiaBase.query.get(metodologia_base_id)
                if metodologia_base:
                    db.session.delete(metodologia_base)
                    metodologias_borradas.append(metodologia_base_id)
        db.session.delete(fraccion)
        db.session.commit()
        mensaje = f"Fraccion {fraccion_id} eliminada correctamente"
        return jsonify({
            "success": True,
            "message": mensaje,
            "metodologias_borradas": metodologias_borradas
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/fracciones/<fraccion_id>/metodologias", methods=["GET"])
@admin_required
def api_fraccion_metodologias_get(fraccion_id):
    """Obtiene las metodologias configuradas para los 4 niveles de una fraccion"""
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        metodologias_data = {}
        for nivel_id in [1, 2, 3, 4]:
            metodologia_asignacion = Metodologia.query.filter_by(
                fraccion_id=fraccion_id,
                nivel_limpieza_id=nivel_id
            ).first()
            if metodologia_asignacion:
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
                metodologias_data[str(nivel_id)] = None
        nombre_full = fraccion.fraccion_nombre
        if fraccion.nombre_custom:
            nombre_full = f"{fraccion.fraccion_nombre} - {fraccion.nombre_custom}"
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


@api_bp.route("/api/fracciones/<fraccion_id>/metodologias/<int:nivel_id>", methods=["POST"])
@admin_required
def api_fraccion_metodologias_save(fraccion_id, nivel_id):
    """Guarda/actualiza la metodologia de un nivel especifico"""
    try:
        fraccion = Fraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        if nivel_id not in [1, 2, 3, 4]:
            return jsonify({"success": False, "error": "Nivel invalido (1-4)"}), 400
        nivel_limpieza = NivelLimpieza.query.get(nivel_id)
        if not nivel_limpieza:
            return jsonify({"success": False, "error": f"Nivel de limpieza {nivel_id} no encontrado"}), 404
        data = request.get_json()
        pasos = data.get("pasos", [])
        if len(pasos) == 0:
            return jsonify({"success": False, "error": "Debe haber al menos 1 paso"}), 400
        for paso in pasos:
            if not paso.get("instruccion", "").strip():
                return jsonify({"success": False, "error": "Todos los pasos deben tener instruccion"}), 400
        nivel_letra_map = {1: 'B', 2: 'M', 3: 'P', 4: 'E'}
        nivel_letra = nivel_letra_map[nivel_id]
        partes = fraccion_id.split('-')
        if len(partes) != 3:
            return jsonify({"success": False, "error": "Formato de fraccion_id invalido"}), 400
        codigo = partes[1]
        numero = partes[2]
        metodologia_base_id = f"MB-{codigo}-{numero}-{nivel_letra}"
        metodologia_base = MetodologiaBase.query.get(metodologia_base_id)
        if not metodologia_base:
            nombre_base = fraccion.fraccion_nombre
            metodologia_base = MetodologiaBase(
                metodologia_base_id=metodologia_base_id,
                nombre=f"{nombre_base}-{nivel_letra}",
                descripcion=fraccion.fraccion_nombre
            )
            db.session.add(metodologia_base)
            db.session.flush()
        MetodologiaBasePaso.query.filter_by(
            metodologia_base_id=metodologia_base_id
        ).delete()
        for paso in pasos:
            nuevo_paso = MetodologiaBasePaso(
                metodologia_base_id=metodologia_base_id,
                orden=paso["orden"],
                instruccion=paso["instruccion"].strip()
            )
            db.session.add(nuevo_paso)
        metodologia_link = Metodologia.query.filter_by(
            fraccion_id=fraccion_id,
            nivel_limpieza_id=nivel_id
        ).first()
        if not metodologia_link:
            metodologia_link = Metodologia(
                fraccion_id=fraccion_id,
                nivel_limpieza_id=nivel_id,
                metodologia_base_id=metodologia_base_id
            )
            db.session.add(metodologia_link)
        else:
            metodologia_link.metodologia_base_id = metodologia_base_id
        db.session.commit()
        return jsonify({
            "success": True,
            "metodologia_base_id": metodologia_base_id,
            "total_pasos": len(pasos),
            "message": f"Metodologia {metodologia_base_id} guardada correctamente"
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - KITS EVENTOS (CRUD)
# =========================

@api_bp.route("/api/kits-eventos/eventos-disponibles", methods=["GET"])
@admin_required
def api_kits_eventos_eventos_disponibles():
    """Retorna eventos disponibles para dropdown"""
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
        return jsonify({"success": True, "eventos": eventos_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kits-eventos/casos-disponibles", methods=["GET"])
@admin_required
def api_kits_eventos_casos_disponibles():
    """Retorna casos disponibles para dropdown"""
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        query = CasoCatalogo.query
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
        return jsonify({"success": True, "casos": casos_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/kits-eventos/next-id", methods=["GET"])
@admin_required
def api_kits_eventos_next_id():
    """Genera el proximo ID disponible para un caso"""
    caso_id = request.args.get("caso_id", "").strip()
    if not caso_id:
        return jsonify({"success": False, "error": "caso_id requerido"}), 400
    try:
        partes = caso_id.split('-')
        if len(partes) < 3:
            return jsonify({"success": False, "error": "Formato de caso_id invalido"}), 400
        codigo = partes[2]
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
        pattern = f"KT-EV-{codigo}-%"
        ultimo = Kit.query.filter(Kit.kit_id.like(pattern)).order_by(Kit.kit_id.desc()).first()
        if ultimo:
            partes_kit = ultimo.kit_id.split('-')
            if len(partes_kit) == 4:
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


@api_bp.route("/api/kits-eventos", methods=["GET"])
@admin_required
def api_kits_eventos_listar():
    """Lista kits de tipo 'evento' con sus herramientas"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        evento_tipo = request.args.get('evento_tipo', '').strip()
        caso = request.args.get('caso', '').strip()
        query = Kit.query.filter_by(tipo_kit='evento')
        if caso:
            query = query.filter_by(caso_id=caso)
        elif evento_tipo:
            query = query.join(CasoCatalogo, Kit.caso_id == CasoCatalogo.caso_id)\
                         .filter(CasoCatalogo.evento_tipo_id == evento_tipo)
        query = query.order_by(Kit.kit_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        kits_data = []
        for k in pagination.items:
            detalles = KitDetalle.query.filter_by(kit_id=k.kit_id).all()
            herramientas = [
                {
                    'herramienta_id': d.herramienta_id,
                    'nombre': d.herramienta.nombre if d.herramienta else '',
                    'nota': d.nota
                }
                for d in detalles
            ]
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


@api_bp.route("/api/kits-eventos", methods=["POST"])
@admin_required
def api_kits_eventos_crear():
    """Crea un nuevo kit de tipo 'evento'"""
    try:
        data = request.get_json()
        caso_id = data.get("caso_id", "").strip()
        nombre = data.get("nombre", "").strip()
        herramientas_ids = data.get("herramientas", [])
        if not caso_id:
            return jsonify({"success": False, "error": "caso_id requerido"}), 400
        caso = CasoCatalogo.query.get(caso_id)
        if not caso:
            return jsonify({"success": False, "error": f"Caso {caso_id} no encontrado"}), 404
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if not herramientas_ids or len(herramientas_ids) == 0:
            return jsonify({"success": False, "error": "Debe seleccionar al menos 1 herramienta"}), 400
        for h_id in herramientas_ids:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        partes = caso_id.split('-')
        if len(partes) < 3:
            return jsonify({"success": False, "error": "Formato de caso_id invalido"}), 400
        codigo = partes[2]
        pattern = f"KT-EV-{codigo}-%"
        ultimo = Kit.query.filter(Kit.kit_id.like(pattern)).order_by(Kit.kit_id.desc()).first()
        if ultimo:
            partes_kit = ultimo.kit_id.split('-')
            numero_actual = int(partes_kit[3]) if len(partes_kit) == 4 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        kit_id = f"KT-EV-{codigo}-{siguiente:03d}"
        nuevo_kit = Kit(
            kit_id=kit_id,
            fraccion_id=None,
            nivel_limpieza_id=None,
            nombre=nombre,
            tipo_kit='evento',
            caso_id=caso_id
        )
        db.session.add(nuevo_kit)
        db.session.flush()
        for h_id in herramientas_ids:
            detalle = KitDetalle(kit_id=kit_id, herramienta_id=h_id, nota=nombre)
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


@api_bp.route("/api/kits-eventos/<kit_id>", methods=["PUT"])
@admin_required
def api_kits_eventos_editar(kit_id):
    """Edita un kit de tipo 'evento' existente"""
    try:
        kit = Kit.query.get(kit_id)
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        if kit.tipo_kit != 'evento':
            return jsonify({"success": False, "error": "Este kit no es de tipo evento"}), 400
        data = request.get_json()
        nuevo_nombre = data.get("nombre", "").strip()
        nuevas_herramientas = data.get("herramientas", [])
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        if not nuevas_herramientas or len(nuevas_herramientas) == 0:
            return jsonify({"success": False, "error": "Debe tener al menos 1 herramienta"}), 400
        for h_id in nuevas_herramientas:
            herr = Herramienta.query.get(h_id)
            if not herr:
                return jsonify({"success": False, "error": f"Herramienta {h_id} no encontrada"}), 404
        kit.nombre = nuevo_nombre
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
        for h_id in nuevas_herramientas:
            detalle = KitDetalle(kit_id=kit_id, herramienta_id=h_id, nota=nuevo_nombre)
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


@api_bp.route("/api/kits-eventos/<kit_id>", methods=["DELETE"])
@admin_required
def api_kits_eventos_eliminar(kit_id):
    """Elimina un kit de tipo 'evento'"""
    try:
        kit = Kit.query.get(kit_id)
        if not kit:
            return jsonify({"success": False, "error": "Kit no encontrado"}), 404
        if kit.tipo_kit != 'evento':
            return jsonify({"success": False, "error": "Este kit no es de tipo evento"}), 400
        KitDetalle.query.filter_by(kit_id=kit_id).delete()
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

@api_bp.route("/api/fracciones-eventos/eventos-disponibles", methods=["GET"])
@admin_required
def api_fracciones_eventos_eventos_disponibles():
    """Retorna eventos disponibles para dropdown"""
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
        return jsonify({"success": True, "eventos": eventos_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/fracciones-eventos/codigos-disponibles", methods=["GET"])
@admin_required
def api_fracciones_eventos_codigos_disponibles():
    """Extrae codigos unicos de fracciones existentes para un evento"""
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        if not evento_tipo:
            return jsonify({"success": False, "error": "evento_tipo requerido"}), 400
        evento = EventoCatalogo.query.get(evento_tipo)
        if not evento:
            return jsonify({"success": False, "error": f"Evento {evento_tipo} no encontrado"}), 404
        partes_evento = evento_tipo.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo invalido"}), 400
        codigo_evento = partes_evento[1]
        pattern = f"FR-{codigo_evento}-%"
        fracciones = SopEventoFraccion.query.filter(
            SopEventoFraccion.evento_tipo_id == evento_tipo,
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(SopEventoFraccion.fraccion_evento_id).all()
        codigos_map = {}
        for f in fracciones:
            partes = f.fraccion_evento_id.split('-')
            if len(partes) >= 3:
                codigo = partes[2]
                if codigo not in codigos_map:
                    codigos_map[codigo] = {
                        "codigo": codigo,
                        "nombre_base": f.nombre,
                        "count": 0,
                        "ultima_fraccion": ""
                    }
                codigos_map[codigo]["count"] += 1
                codigos_map[codigo]["ultima_fraccion"] = f.fraccion_evento_id
        codigos_data = sorted(codigos_map.values(), key=lambda x: x["codigo"])
        return jsonify({"success": True, "codigos": codigos_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/fracciones-eventos/next-id", methods=["GET"])
@admin_required
def api_fracciones_eventos_next_id():
    """Genera el proximo ID disponible para una fraccion de evento"""
    try:
        evento_tipo = request.args.get("evento_tipo", "").strip()
        codigo = request.args.get("codigo", "").strip().upper()
        if not evento_tipo or not codigo:
            return jsonify({"success": False, "error": "evento_tipo y codigo requeridos"}), 400
        partes_evento = evento_tipo.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo invalido"}), 400
        codigo_evento = partes_evento[1]
        if len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
        pattern = f"FR-{codigo_evento}-{codigo}-%"
        ultima = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(SopEventoFraccion.fraccion_evento_id.desc()).first()
        if ultima:
            partes = ultima.fraccion_evento_id.split('-')
            if len(partes) == 4:
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


@api_bp.route("/api/fracciones-eventos", methods=["GET"])
@admin_required
def api_fracciones_eventos_listar():
    """Lista fracciones de eventos con info de metodologia"""
    try:
        evento_tipo = request.args.get('evento_tipo', '').strip()
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        query = SopEventoFraccion.query
        if evento_tipo:
            query = query.filter_by(evento_tipo_id=evento_tipo)
        query = query.order_by(SopEventoFraccion.fraccion_evento_id.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        fracciones_data = []
        for f in pagination.items:
            partes = f.fraccion_evento_id.split('-')
            codigo = partes[2] if len(partes) >= 3 else ''
            metodologia = MetodologiaEventoFraccion.query.filter_by(
                fraccion_evento_id=f.fraccion_evento_id
            ).first()
            tiene_metodologia = metodologia is not None
            cantidad_pasos = 0
            if metodologia:
                cantidad_pasos = MetodologiaEventoFraccionPaso.query.filter_by(
                    metodologia_fraccion_id=metodologia.metodologia_fraccion_id
                ).count()
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


@api_bp.route("/api/fracciones-eventos", methods=["POST"])
@admin_required
def api_fracciones_eventos_crear():
    """Crea una nueva fraccion de evento + metodologia automatica"""
    try:
        data = request.get_json()
        evento_tipo_id = data.get("evento_tipo_id", "").strip()
        codigo = data.get("codigo", "").strip().upper()
        nombre = data.get("nombre", "").strip()
        descripcion = data.get("descripcion", "").strip()
        if not evento_tipo_id:
            return jsonify({"success": False, "error": "evento_tipo_id requerido"}), 400
        evento = EventoCatalogo.query.get(evento_tipo_id)
        if not evento:
            return jsonify({"success": False, "error": f"Evento {evento_tipo_id} no encontrado"}), 404
        if not codigo or len(codigo) != 2:
            return jsonify({"success": False, "error": "Codigo debe tener 2 caracteres"}), 400
        if not nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
        partes_evento = evento_tipo_id.split('-')
        if len(partes_evento) < 2:
            return jsonify({"success": False, "error": "Formato de evento_tipo_id invalido"}), 400
        codigo_evento = partes_evento[1]
        pattern = f"FR-{codigo_evento}-{codigo}-%"
        nombre_existente = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern),
            SopEventoFraccion.nombre == nombre
        ).first()
        if nombre_existente:
            return jsonify({
                "success": False,
                "error": f"Ya existe una fraccion con el nombre '{nombre}'"
            }), 400
        ultima = SopEventoFraccion.query.filter(
            SopEventoFraccion.fraccion_evento_id.like(pattern)
        ).order_by(SopEventoFraccion.fraccion_evento_id.desc()).first()
        if ultima:
            partes = ultima.fraccion_evento_id.split('-')
            numero_actual = int(partes[3]) if len(partes) == 4 else 0
            siguiente = numero_actual + 1
        else:
            siguiente = 1
        fraccion_evento_id = f"FR-{codigo_evento}-{codigo}-{siguiente:03d}"
        nueva_fraccion = SopEventoFraccion(
            fraccion_evento_id=fraccion_evento_id,
            evento_tipo_id=evento_tipo_id,
            nombre=nombre,
            descripcion=descripcion
        )
        db.session.add(nueva_fraccion)
        db.session.flush()
        metodologia_id = f"ME-{codigo_evento}-{codigo}-{siguiente:03d}"
        nombre_metodologia = f"Metodologia de {nombre}"
        nueva_metodologia = MetodologiaEventoFraccion(
            metodologia_fraccion_id=metodologia_id,
            fraccion_evento_id=fraccion_evento_id,
            nombre=nombre_metodologia,
            descripcion=descripcion
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


@api_bp.route("/api/fracciones-eventos/<fraccion_id>", methods=["PUT"])
@admin_required
def api_fracciones_eventos_editar(fraccion_id):
    """Edita una fraccion de evento existente"""
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        data = request.get_json()
        nuevo_nombre = data.get("nombre", "").strip()
        nueva_descripcion = data.get("descripcion", "").strip()
        if not nuevo_nombre:
            return jsonify({"success": False, "error": "Nombre requerido"}), 400
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
                    "error": f"Ya existe otra fraccion con el nombre '{nuevo_nombre}'"
                }), 400
        fraccion.nombre = nuevo_nombre
        fraccion.descripcion = nueva_descripcion
        metodologia = MetodologiaEventoFraccion.query.filter_by(
            fraccion_evento_id=fraccion_id
        ).first()
        if metodologia:
            metodologia.nombre = f"Metodologia de {nuevo_nombre}"
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


@api_bp.route("/api/fracciones-eventos/<fraccion_id>", methods=["DELETE"])
@admin_required
def api_fracciones_eventos_eliminar(fraccion_id):
    """Elimina una fraccion de evento"""
    try:
        fraccion = SopEventoFraccion.query.get(fraccion_id)
        if not fraccion:
            return jsonify({"success": False, "error": "Fraccion no encontrada"}), 404
        en_uso = SopEventoDetalle.query.filter_by(fraccion_evento_id=fraccion_id).count()
        if en_uso > 0:
            return jsonify({
                "success": False,
                "error": f"No se puede eliminar. Esta fraccion esta en uso en {en_uso} SOP(s)"
            }), 400
        db.session.delete(fraccion)
        db.session.commit()
        return jsonify({
            "success": True,
            "message": f"Fraccion {fraccion_id} eliminada correctamente"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API - METODOLOGIAS EVENTOS
# =========================

@api_bp.route("/api/metodologias-eventos/<metodologia_id>", methods=["GET"])
@admin_required
def api_metodologia_evento_get(metodologia_id):
    """Obtiene los datos de una metodologia de evento con sus pasos"""
    try:
        metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)
        if not metodologia:
            return jsonify({"success": False, "error": "Metodologia no encontrada"}), 404
        pasos = []
        for paso in metodologia.pasos:
            pasos.append({
                "numero_paso": paso.numero_paso,
                "descripcion": paso.descripcion
            })
        fraccion = metodologia.fraccion
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


@api_bp.route("/api/metodologias-eventos/<metodologia_id>/pasos", methods=["POST"])
@admin_required
def api_metodologia_evento_save_pasos(metodologia_id):
    """Guarda/actualiza los pasos de una metodologia de evento"""
    try:
        metodologia = MetodologiaEventoFraccion.query.get(metodologia_id)
        if not metodologia:
            return jsonify({"success": False, "error": "Metodologia no encontrada"}), 404
        data = request.get_json()
        pasos = data.get("pasos", [])
        if len(pasos) == 0:
            return jsonify({"success": False, "error": "Debe haber al menos 1 paso"}), 400
        for paso in pasos:
            if not paso.get("descripcion", "").strip():
                return jsonify({"success": False, "error": "Todos los pasos deben tener descripcion"}), 400
        MetodologiaEventoFraccionPaso.query.filter_by(
            metodologia_fraccion_id=metodologia_id
        ).delete()
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
            "message": f"Metodologia {metodologia_id} guardada correctamente"
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
