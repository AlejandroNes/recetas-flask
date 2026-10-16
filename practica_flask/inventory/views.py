"""Authenticated screens for inventory and recipes."""

from datetime import timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from practica_flask.extensions import db

from .forms import (
    ActionForm,
    CategoriaForm,
    IngredienteForm,
    MovimientoForm,
    PlatoForm,
    PreparacionForm,
    RecetaForm,
)
from .models import (
    Categoria,
    Ingrediente,
    MovimientoInventario,
    Plato,
    Receta,
    local_today,
)
from .services import StockError, move_stock, prepare_dish

blueprint = Blueprint("inventory", __name__, url_prefix="/cocina")


@blueprint.before_request
@login_required
def require_login():
    """Every inventory endpoint requires a session."""


@blueprint.app_context_processor
def shared_context():
    """Provide CSRF action forms and the local date to templates."""
    return {"action_form": ActionForm(), "today": local_today()}


@blueprint.app_template_filter("localtime")
def local_time(value):
    """Display a UTC database timestamp in the business timezone."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("America/La_Paz")).strftime("%d/%m/%Y %H:%M")


@blueprint.app_template_filter("qty")
def format_quantity(value):
    """Display up to three decimal places without trailing zeroes."""
    return format(Decimal(value), ".3f").rstrip("0").rstrip(".")


@blueprint.app_template_filter("money")
def format_money(value):
    """Display monetary values with exactly two decimal places."""
    return f"{value:,.2f}"


def get_or_404(model, identifier):
    """Load one ORM entity or return a not-found response."""
    return db.get_or_404(model, identifier)


def save_record(record, form, fields, destination, **route_values):
    """Validate and persist editable fields, handling uniqueness errors."""
    if form.validate_on_submit():
        for field in fields:
            value = form[field].data
            setattr(record, field, value.strip() if isinstance(value, str) else value)
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "No se pudo guardar: revisa el nombre duplicado o las relaciones.",
                "danger",
            )
        else:
            flash("Cambios guardados.", "success")
            return redirect(url_for(destination, **route_values))
    return None


@blueprint.get("/")
def dashboard():
    """Summarize active stock, exceptions and recent movements."""
    ingredientes = db.session.scalars(
        select(Ingrediente)
        .options(joinedload(Ingrediente.categoria))
        .where(Ingrediente.activo.is_(True))
        .order_by(Ingrediente.nombre)
    ).all()
    low = [
        i for i in ingredientes if i.cantidad <= i.stock_minimo and i.categoria.activo
    ]
    expired = [i for i in ingredientes if i.vencido and i.categoria.activo]
    movements = db.session.scalars(
        select(MovimientoInventario)
        .options(
            joinedload(MovimientoInventario.ingrediente),
            joinedload(MovimientoInventario.usuario),
        )
        .order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.id.desc())
        .limit(6)
    ).all()
    return render_template(
        "inventory/dashboard.html",
        title="Tu cocina, en orden",
        ingredients=ingredientes,
        low=low,
        expired=expired,
        movements=movements,
        dishes=db.session.scalar(
            select(func.count()).select_from(Plato).where(Plato.activo.is_(True))
        ),
        value=sum((i.cantidad * i.costo_unitario for i in ingredientes), Decimal("0")),
    )


@blueprint.get("/categorias/")
def categories():
    """List all categories, including inactive ones."""
    rows = db.session.scalars(select(Categoria).order_by(Categoria.nombre)).all()
    return render_template("inventory/categories.html", title="Categorías", rows=rows)


@blueprint.route("/categorias/nueva/", methods=["GET", "POST"])
@blueprint.route("/categorias/<int:identifier>/editar/", methods=["GET", "POST"])
def category_form(identifier=None):
    """Create or update a category."""
    record = get_or_404(Categoria, identifier) if identifier else Categoria()
    form = CategoriaForm(obj=record)
    response = save_record(
        record, form, ["nombre", "descripcion"], "inventory.categories"
    )
    return response or render_template(
        "inventory/form.html",
        form=form,
        title="Editar categoría" if identifier else "Nueva categoría",
        back=url_for("inventory.categories"),
        note="Agrupa tus ingredientes para encontrarlos con facilidad.",
    )


@blueprint.get("/ingredientes/")
def ingredients():
    """Search stock by name, category and availability filters."""
    q = request.args.get("q", "").strip()
    category = request.args.get("categoria", type=int)
    status = request.args.get("estado", "")
    stmt = (
        select(Ingrediente)
        .options(joinedload(Ingrediente.categoria))
        .order_by(Ingrediente.nombre)
    )
    if q:
        stmt = stmt.where(Ingrediente.nombre.icontains(q, autoescape=True))
    if category:
        stmt = stmt.where(Ingrediente.categoria_id == category)
    if status == "bajo":
        stmt = stmt.where(
            Ingrediente.cantidad <= Ingrediente.stock_minimo,
            Ingrediente.activo.is_(True),
        )
    elif status == "vencido":
        stmt = stmt.where(
            Ingrediente.fecha_vencimiento < local_today(), Ingrediente.activo.is_(True)
        )
    return render_template(
        "inventory/ingredients.html",
        title="Despensa",
        rows=db.session.scalars(stmt).all(),
        categories=db.session.scalars(
            select(Categoria).order_by(Categoria.nombre)
        ).all(),
        q=q,
        category=category,
        status=status,
    )


@blueprint.route("/ingredientes/nuevo/", methods=["GET", "POST"])
@blueprint.route("/ingredientes/<int:identifier>/editar/", methods=["GET", "POST"])
def ingredient_form(identifier=None):
    """Edit ingredient metadata while protecting historic units."""
    record = (
        get_or_404(Ingrediente, identifier)
        if identifier
        else Ingrediente(costo_unitario=0, stock_minimo=0)
    )
    form = IngredienteForm(obj=record)
    cats = db.session.scalars(
        select(Categoria).where(Categoria.activo.is_(True)).order_by(Categoria.nombre)
    ).all()
    form.categoria_id.choices = [(c.id, c.nombre) for c in cats]
    if not cats:
        flash("Primero crea o activa una categoría.", "warning")
        return redirect(url_for("inventory.categories"))
    # A unit change after any movement would reinterpret its entire history.
    if (
        request.method == "POST"
        and identifier
        and form.unidad_medida.data != record.unidad_medida
    ):
        used = db.session.scalar(
            select(MovimientoInventario.id)
            .where(MovimientoInventario.ingrediente_id == identifier)
            .limit(1)
        ) or db.session.scalar(
            select(Receta.id).where(Receta.ingrediente_id == identifier).limit(1)
        )
        if used:
            flash(
                "No puedes cambiar la unidad de un ingrediente con movimientos o recetas.",
                "danger",
            )
            return render_template(
                "inventory/form.html",
                form=form,
                title="Editar ingrediente",
                back=url_for("inventory.ingredients"),
            )
    response = save_record(
        record,
        form,
        [
            "nombre",
            "categoria_id",
            "unidad_medida",
            "costo_unitario",
            "stock_minimo",
            "fecha_vencimiento",
        ],
        "inventory.ingredients",
    )
    return response or render_template(
        "inventory/form.html",
        form=form,
        title="Editar ingrediente" if identifier else "Nuevo ingrediente",
        back=url_for("inventory.ingredients"),
        note=(
            "El stock inicial es cero. Registra una entrada para sumar existencias. "
            "Todas las cantidades usan la unidad elegida."
        ),
    )


@blueprint.get("/platos/")
def dishes():
    """List dishes with their calculated recipe costs."""
    rows = db.session.scalars(select(Plato).order_by(Plato.nombre)).all()
    return render_template("inventory/dishes.html", title="Platos y recetas", rows=rows)


@blueprint.route("/platos/nuevo/", methods=["GET", "POST"])
@blueprint.route("/platos/<int:identifier>/editar/", methods=["GET", "POST"])
def dish_form(identifier=None):
    """Create or update a dish."""
    record = get_or_404(Plato, identifier) if identifier else Plato(precio=0)
    form = PlatoForm(obj=record)
    response = save_record(
        record, form, ["nombre", "descripcion", "precio"], "inventory.dishes"
    )
    return response or render_template(
        "inventory/form.html",
        form=form,
        title="Editar plato" if identifier else "Nuevo plato",
        back=url_for("inventory.dishes"),
        note="Después de guardar, abre su receta para definir los ingredientes por porción.",
    )


@blueprint.route("/platos/<int:identifier>/receta/", methods=["GET", "POST"])
@blueprint.route(
    "/platos/<int:identifier>/receta/<int:line_id>/editar/", methods=["GET", "POST"]
)
def recipe(identifier, line_id=None):
    """Manage the ingredient quantities required by one dish."""
    dish = get_or_404(Plato, identifier)
    line = get_or_404(Receta, line_id) if line_id else Receta(plato_id=dish.id)
    if line_id and line.plato_id != dish.id:
        abort(404)
    form = RecetaForm(obj=line)
    choices = db.session.scalars(
        select(Ingrediente)
        .join(Ingrediente.categoria)
        .where(Ingrediente.activo.is_(True), Categoria.activo.is_(True))
        .order_by(Ingrediente.nombre)
    ).all()
    form.ingrediente_id.choices = [
        (i.id, f"{i.nombre} ({i.unidad_medida})") for i in choices
    ]
    if form.validate_on_submit():
        line.ingrediente_id = form.ingrediente_id.data
        line.cantidad_necesaria = form.cantidad_necesaria.data
        db.session.add(line)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Ese ingrediente ya está en la receta. Edita su cantidad.", "danger")
        else:
            flash("Receta guardada.", "success")
            return redirect(url_for("inventory.recipe", identifier=dish.id))
    return render_template(
        "inventory/recipe.html",
        title=dish.nombre,
        dish=dish,
        form=form,
        editing=bool(line_id),
        preparation=PreparacionForm(),
        choices=choices,
    )


@blueprint.post("/recetas/<int:identifier>/quitar/")
def recipe_remove(identifier):
    """Remove a recipe component without modifying existing stock."""
    line = get_or_404(Receta, identifier)
    dish_id = line.plato_id
    if ActionForm().validate_on_submit():
        db.session.delete(line)
        db.session.commit()
        flash("Ingrediente retirado de la receta.", "success")
    return redirect(url_for("inventory.recipe", identifier=dish_id))


@blueprint.post("/platos/<int:identifier>/preparar/")
def prepare(identifier):
    """Commit every ingredient deduction or rollback the preparation."""
    dish = get_or_404(Plato, identifier)
    form = PreparacionForm()
    if form.validate_on_submit():
        try:
            prepare_dish(dish, form.porciones.data, current_user.id)
            db.session.commit()
        except StockError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash(
                "Preparación registrada. Se descontaron los ingredientes de la despensa.",
                "success",
            )
    else:
        flash("Indica entre 1 y 1000 porciones enteras.", "danger")
    return redirect(url_for("inventory.recipe", identifier=identifier))


@blueprint.get("/movimientos/")
def movements():
    """Show the immutable history in pages of thirty rows."""
    page = max(1, request.args.get("page", 1, type=int))
    stmt = (
        select(MovimientoInventario)
        .options(
            joinedload(MovimientoInventario.ingrediente),
            joinedload(MovimientoInventario.usuario),
        )
        .order_by(MovimientoInventario.fecha.desc(), MovimientoInventario.id.desc())
    )
    pagination = db.paginate(stmt, page=page, per_page=30, error_out=False)
    return render_template(
        "inventory/movements.html", title="Movimientos", pagination=pagination
    )


@blueprint.route("/movimientos/nuevo/", methods=["GET", "POST"])
def movement_form():
    """Record a validated stock movement and its operator."""
    form = MovimientoForm()
    choices = db.session.scalars(
        select(Ingrediente)
        .join(Ingrediente.categoria)
        .where(Ingrediente.activo.is_(True), Categoria.activo.is_(True))
        .order_by(Ingrediente.nombre)
    ).all()
    form.ingrediente_id.choices = [
        (i.id, f"{i.nombre} · {i.cantidad} {i.unidad_medida}") for i in choices
    ]
    if not choices:
        flash(
            "Crea o activa un ingrediente y su categoría para registrar movimientos.",
            "warning",
        )
        return redirect(url_for("inventory.ingredients"))
    if request.method == "GET" and request.args.get("ingrediente", type=int) in [
        i.id for i in choices
    ]:
        form.ingrediente_id.data = request.args.get("ingrediente", type=int)
    if form.validate_on_submit():
        ingredient = get_or_404(Ingrediente, form.ingrediente_id.data)
        try:
            move_stock(
                ingredient,
                form.tipo.data,
                form.cantidad.data,
                form.motivo.data.strip(),
                current_user.id,
            )
            db.session.commit()
        except StockError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash("Movimiento registrado.", "success")
            return redirect(url_for("inventory.movements"))
    return render_template(
        "inventory/form.html",
        form=form,
        title="Registrar movimiento",
        back=url_for("inventory.movements"),
        note=(
            "La cantidad usa la unidad del ingrediente. Las salidas no pueden dejar stock negativo. "
            "El historial no se edita: registra otro movimiento para corregirlo."
        ),
    )


@blueprint.post("/<string:kind>/<int:identifier>/estado/")
def toggle(kind, identifier):
    """Activate or deactivate records while preserving their history."""
    models = {
        "categorias": (Categoria, "inventory.categories"),
        "ingredientes": (Ingrediente, "inventory.ingredients"),
        "platos": (Plato, "inventory.dishes"),
    }
    if kind not in models:
        abort(404)
    model, destination = models[kind]
    record = get_or_404(model, identifier)
    if ActionForm().validate_on_submit():
        record.activo = not record.activo
        db.session.commit()
        flash("Estado actualizado. Se conserva el historial.", "success")
    return redirect(url_for(destination))
