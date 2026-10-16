"""Session-based authentication with CSRF and safe local redirects."""

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from practica_flask.extensions import db, login_manager
from practica_flask.inventory.forms import ActionForm
from practica_flask.public.forms import LoginForm, RegisterForm
from practica_flask.user.models import User

blueprint = Blueprint("public", __name__)


@login_manager.user_loader
def load_user(user_id):
    """Restore an authenticated user from a session identifier."""
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def safe_next(value):
    """Accept only a relative URL within this application."""
    if not value or "\\" in value or any(ord(c) < 32 for c in value):
        return None
    if not value.startswith("/") or value.startswith("//"):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return (
        value
        if value.startswith("/")
        and not value.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
        else None
    )


@blueprint.route("/")
def home():
    """Send the visitor to the login screen or their kitchen."""
    return redirect(
        url_for(
            "inventory.dashboard" if current_user.is_authenticated else "public.login"
        )
    )


@blueprint.route("/login/", methods=["GET", "POST"])
def login():
    """Authenticate an account and open its requested local page."""
    if current_user.is_authenticated:
        return redirect(url_for("inventory.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            select(User).where(User.username == form.username.data.strip().lower())
        )
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(
                safe_next(request.args.get("next")) or url_for("inventory.dashboard")
            )
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("auth/login.html", form=form, title="Iniciar sesión")


@blueprint.route("/register/", methods=["GET", "POST"])
def register():
    """Create an account without storing a plaintext password."""
    if current_user.is_authenticated:
        return redirect(url_for("inventory.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data.strip().lower())
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.username.errors.append("Ese usuario ya existe.")
        else:
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("public.login"))
    return render_template("auth/register.html", form=form, title="Crear cuenta")


@blueprint.post("/logout/")
@login_required
def logout():
    """Close the current session after validating a CSRF token."""
    form = ActionForm()
    if form.validate_on_submit():
        logout_user()
        flash("Sesión cerrada.", "success")
    return redirect(url_for("public.login"))
