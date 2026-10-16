"""Atomic stock changes and immutable movement history."""

from decimal import Decimal

from sqlalchemy import func, update

from practica_flask.extensions import db

from .models import Ingrediente, MovimientoInventario

MAX_STOCK = Decimal("999999999.999")


class StockError(ValueError):
    """An inventory operation could not be completed."""


def move_stock(ingrediente, tipo, cantidad, motivo, usuario_id):
    """Stage an atomic stock update and its audit row; the caller commits."""
    if (
        tipo not in ("entrada", "salida")
        or not cantidad.is_finite()
        or cantidad <= 0
        or cantidad > MAX_STOCK
    ):
        raise StockError(
            "El movimiento debe tener una cantidad positiva y un tipo válido."
        )
    if cantidad != cantidad.quantize(Decimal(".001")):
        raise StockError("La cantidad admite como máximo tres decimales.")
    if not ingrediente.activo or not ingrediente.categoria.activo:
        raise StockError(
            "Activa el ingrediente y su categoría antes de registrar movimientos."
        )
    if tipo == "entrada" and ingrediente.vencido:
        raise StockError("Actualiza la fecha de vencimiento antes de ingresar stock.")
    delta = cantidad if tipo == "entrada" else -cantidad
    statement = update(Ingrediente).where(Ingrediente.id == ingrediente.id)
    if tipo == "salida":
        statement = statement.where(Ingrediente.cantidad >= cantidad)
    else:
        statement = statement.where(Ingrediente.cantidad <= MAX_STOCK - cantidad)
    result = db.session.execute(
        statement.values(
            cantidad=func.round(Ingrediente.cantidad + delta, 3)
        ).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise StockError(
            f"Stock insuficiente o fuera de límite para {ingrediente.nombre}."
        )
    db.session.add(
        MovimientoInventario(
            ingrediente_id=ingrediente.id,
            usuario_id=usuario_id,
            tipo=tipo,
            cantidad=cantidad,
            motivo=motivo,
        )
    )
    db.session.expire(ingrediente, ["cantidad"])


def prepare_dish(plato, porciones, usuario_id):
    """Stage all deductions; callers must rollback the whole transaction on error."""
    if not plato.activo or not plato.recetas:
        raise StockError("El plato debe estar activo y tener una receta.")
    if not isinstance(porciones, int) or not 1 <= porciones <= 1000:
        raise StockError("Indica entre 1 y 1000 porciones.")
    for receta in sorted(plato.recetas, key=lambda r: r.ingrediente_id):
        if not receta.ingrediente.disponible:
            raise StockError(f"{receta.ingrediente.nombre} está vencido o inactivo.")
        move_stock(
            receta.ingrediente,
            "salida",
            receta.cantidad_necesaria * porciones,
            f"Preparación: {plato.nombre} ({porciones} porciones)",
            usuario_id,
        )
