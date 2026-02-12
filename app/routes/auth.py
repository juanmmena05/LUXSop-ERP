# auth.py - Blueprint de autenticación
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required

from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas.", "warning")
            return render_template("auth/login.html"), 401

        login_user(user)

        # admin al home, operativo a su ruta
        if user.role == "admin":
            return redirect(url_for("home.home"))
        return redirect(url_for("rutas.mi_ruta"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
