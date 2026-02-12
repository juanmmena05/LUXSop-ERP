# home.py - Blueprint de página principal
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from .helpers import admin_required, get_monday, today_cdmx
from ..extensions import db
from ..models import (
    LanzamientoDia, LanzamientoTarea,
    PlantillaSemanal, PlantillaSemanaAplicada,
)

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
@login_required
def home():
    # admin -> panel semanal
    if getattr(current_user, "role", None) == "admin":
        return redirect(url_for("home.home_admin_panel"))

    # operativo -> su ruta de hoy
    return redirect(url_for("rutas.mi_ruta"))


@home_bp.route("/admin")
@admin_required
def home_admin_panel():
    hoy = today_cdmx()
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
            "link_ruta": url_for("rutas.ruta_dia", fecha=fecha_dia.strftime("%Y-%m-%d")),
            "link_plan": url_for("rutas.plan_dia_asignar", fecha=fecha_dia.strftime("%Y-%m-%d")),
        })

    sabado = lunes + timedelta(days=5)

    plantillas = PlantillaSemanal.query.order_by(PlantillaSemanal.nombre.asc()).all()
    plantilla_activa = PlantillaSemanaAplicada.query.get(lunes)

    return render_template(
        "home/home.html",
        dias_semana=dias_semana,
        lunes=lunes,
        sabado=sabado,
        semana_num=semana_num,
        plantillas=plantillas,
        plantilla_activa=plantilla_activa,
        hide_nav=False,
    )
