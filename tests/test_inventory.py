"""End-to-end business behavior for the inventory screens."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from practica_flask.inventory.models import (
    Categoria,
    Ingrediente,
    MovimientoInventario,
    Plato,
    Receta,
    local_today,
)


def post_move(auth, ingredient, quantity, tipo="entrada"):
    return auth.post(
        "/cocina/movimientos/nuevo/",
        data={
            "ingrediente_id": ingredient.id,
            "cantidad": quantity,
            "tipo": tipo,
            "motivo": "Compra de prueba",
        },
        follow_redirects=True,
    )


def count(db, model):
    return db.session.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize(
    "path",
    [
        "/cocina/",
        "/cocina/categorias/",
        "/cocina/ingredientes/",
        "/cocina/platos/",
        "/cocina/movimientos/",
        "/cocina/categorias/nueva/",
        "/cocina/platos/nuevo/",
    ],
)
def test_empty_screens(auth, path):
    assert auth.get(path).status_code == 200


def test_category_create_edit_duplicate_and_toggle(auth, db):
    assert (
        auth.post(
            "/cocina/categorias/nueva/",
            data={"nombre": "Secos", "descripcion": "Granos"},
        ).status_code
        == 302
    )
    cat = db.session.scalar(select(Categoria))
    assert (
        auth.post("/cocina/categorias/nueva/", data={"nombre": "Secos"}).status_code
        == 200
    )
    assert count(db, Categoria) == 1
    auth.post(
        f"/cocina/categorias/{cat.id}/editar/",
        data={"nombre": "Granos", "descripcion": "Arroz"},
    )
    assert cat.nombre == "Granos"
    auth.post(f"/cocina/categorias/{cat.id}/estado/")
    assert not cat.activo
    auth.post(f"/cocina/categorias/{cat.id}/estado/")
    assert cat.activo


def test_blank_category_rejected(auth, db):
    auth.post("/cocina/categorias/nueva/", data={"nombre": "   "})
    assert count(db, Categoria) == 0


def test_ingredient_create_edit_filter(auth, catalog, db):
    cat, first, second, dish = catalog
    data = {
        "nombre": "Quinua",
        "categoria_id": cat.id,
        "unidad_medida": "kg",
        "costo_unitario": "24.50",
        "stock_minimo": "2.125",
        "fecha_vencimiento": "",
    }
    assert auth.post("/cocina/ingredientes/nuevo/", data=data).status_code == 302
    ingredient = db.session.scalar(
        select(Ingrediente).where(Ingrediente.nombre == "Quinua")
    )
    assert ingredient.cantidad == 0 and ingredient.costo_unitario == Decimal("24.50")
    data["nombre"] = "Quinua real"
    assert (
        auth.post(
            f"/cocina/ingredientes/{ingredient.id}/editar/", data=data
        ).status_code
        == 302
    )
    response = auth.get("/cocina/ingredientes/?q=Quinua")
    assert "Quinua real" in response.text and "Tomate" not in response.text
    response = auth.get("/cocina/ingredientes/?estado=bajo")
    assert "Cebolla" in response.text and "Tomate" not in response.text
    data["categoria_id"] = 999
    assert auth.post("/cocina/ingredientes/nuevo/", data=data).status_code == 200
    assert count(db, Ingrediente) == 3


def test_referenced_unit_cannot_change(auth, catalog):
    cat, first, *_ = catalog
    response = auth.post(
        f"/cocina/ingredientes/{first.id}/editar/",
        data={
            "nombre": first.nombre,
            "categoria_id": cat.id,
            "unidad_medida": "g",
            "costo_unitario": "8",
            "stock_minimo": "2",
        },
    )
    assert "No puedes cambiar la unidad" in response.text
    assert first.unidad_medida == "kg"


def test_moves_are_exact_and_attributed(auth, catalog, db, user):
    _, ingredient, *_ = catalog
    ingredient.cantidad = Decimal("0")
    db.session.commit()
    post_move(auth, ingredient, "0.300")
    post_move(auth, ingredient, "0.100", "salida")
    post_move(auth, ingredient, "0.200", "salida")
    db.session.refresh(ingredient)
    assert ingredient.cantidad == Decimal("0.000")
    moves = db.session.scalars(select(MovimientoInventario)).all()
    assert len(moves) == 3 and all(m.usuario_id == user.id for m in moves)
    assert (
        sum(
            (m.cantidad if m.tipo == "entrada" else -m.cantidad for m in moves),
            Decimal(0),
        )
        == 0
    )


@pytest.mark.parametrize(
    "quantity",
    ["0", "-1", "0.0001", "NaN", "Infinity", "1e1000", "1000000000", "abc", ""],
)
def test_invalid_movement_does_not_change_stock(auth, catalog, db, quantity):
    _, ingredient, *_ = catalog
    response = post_move(auth, ingredient, quantity)
    assert response.status_code == 200
    assert count(db, MovimientoInventario) == 0
    db.session.refresh(ingredient)
    assert ingredient.cantidad == Decimal("5")


def test_insufficient_stock_is_rejected(auth, catalog, db):
    _, ingredient, *_ = catalog
    response = post_move(auth, ingredient, "6", "salida")
    assert "Stock insuficiente" in response.text
    assert ingredient.cantidad == Decimal("5")
    assert count(db, MovimientoInventario) == 0


def test_expired_stock_can_only_leave(auth, catalog, db):
    _, ingredient, *_ = catalog
    ingredient.fecha_vencimiento = local_today() - timedelta(days=1)
    db.session.commit()
    assert "vencimiento" in post_move(auth, ingredient, "1").text
    assert count(db, MovimientoInventario) == 0
    assert "Movimiento registrado" in post_move(auth, ingredient, "1", "salida").text
    assert ingredient.cantidad == 4
    assert "Vencido" in auth.get("/cocina/ingredientes/?estado=vencido").text


def test_inactive_category_prevents_moves(auth, catalog, db):
    cat, ingredient, *_ = catalog
    cat.activo = False
    db.session.commit()
    post_move(auth, ingredient, "1")
    assert count(db, MovimientoInventario) == 0


def test_preparation_deducts_all_and_logs(auth, catalog, db):
    _, first, second, dish = catalog
    response = auth.post(
        f"/cocina/platos/{dish.id}/preparar/",
        data={"porciones": 2},
        follow_redirects=True,
    )
    assert "Preparación registrada" in response.text
    db.session.refresh(first)
    db.session.refresh(second)
    assert first.cantidad == Decimal("4.600") and second.cantidad == Decimal(".800")
    assert count(db, MovimientoInventario) == 2
    assert dish.costo == Decimal("2.20000")


def test_preparation_rolls_back_partial_deduction(auth, catalog, db):
    _, first, second, dish = catalog
    second.cantidad = Decimal(".050")
    db.session.commit()
    response = auth.post(
        f"/cocina/platos/{dish.id}/preparar/",
        data={"porciones": 1},
        follow_redirects=True,
    )
    assert "Stock insuficiente" in response.text
    db.session.refresh(first)
    db.session.refresh(second)
    assert first.cantidad == 5 and second.cantidad == Decimal(".050")
    assert count(db, MovimientoInventario) == 0


@pytest.mark.parametrize(
    "state",
    [
        "expired",
        "inactive_ingredient",
        "inactive_dish",
        "empty_recipe",
        "inactive_category",
    ],
)
def test_unavailable_recipe_rejected(auth, catalog, db, state):
    cat, first, second, dish = catalog
    if state == "expired":
        first.fecha_vencimiento = local_today() - timedelta(days=1)
    elif state == "inactive_ingredient":
        first.activo = False
    elif state == "inactive_dish":
        dish.activo = False
    elif state == "empty_recipe":
        dish.recetas.clear()
    else:
        cat.activo = False
    db.session.commit()
    auth.post(f"/cocina/platos/{dish.id}/preparar/", data={"porciones": 1})
    assert count(db, MovimientoInventario) == 0
    db.session.refresh(first)
    assert first.cantidad == 5


@pytest.mark.parametrize("portions", ["0", "-1", "1001", "1.5", "x"])
def test_invalid_portions(auth, catalog, db, portions):
    dish = catalog[3]
    auth.post(f"/cocina/platos/{dish.id}/preparar/", data={"porciones": portions})
    assert count(db, MovimientoInventario) == 0


def test_dish_and_recipe_create_edit_remove(auth, catalog, db):
    _, first, second, _ = catalog
    response = auth.post(
        "/cocina/platos/nuevo/",
        data={"nombre": "Sopa", "descripcion": "Casera", "precio": "12.50"},
    )
    assert response.status_code == 302
    dish = db.session.scalar(select(Plato).where(Plato.nombre == "Sopa"))
    auth.post(
        f"/cocina/platos/{dish.id}/editar/",
        data={"nombre": "Sopa nueva", "descripcion": "Casera", "precio": "14"},
    )
    assert dish.nombre == "Sopa nueva"
    endpoint = f"/cocina/platos/{dish.id}/receta/"
    assert (
        auth.post(
            endpoint, data={"ingrediente_id": first.id, "cantidad_necesaria": ".125"}
        ).status_code
        == 302
    )
    line = db.session.scalar(select(Receta).where(Receta.plato_id == dish.id))
    response = auth.post(
        endpoint, data={"ingrediente_id": first.id, "cantidad_necesaria": ".500"}
    )
    assert "ya está en la receta" in response.text
    auth.post(
        endpoint + f"{line.id}/editar/",
        data={"ingrediente_id": first.id, "cantidad_necesaria": ".250"},
    )
    assert line.cantidad_necesaria == Decimal(".250")
    assert (
        auth.get(f"/cocina/platos/{catalog[3].id}/receta/{line.id}/editar/").status_code
        == 404
    )
    auth.post(f"/cocina/recetas/{line.id}/quitar/")
    assert db.session.get(Receta, line.id) is None
    assert first.cantidad == 5


def test_missing_records_are_404(auth):
    for path in [
        "/cocina/platos/999/receta/",
        "/cocina/ingredientes/999/editar/",
        "/no-existe",
    ]:
        assert auth.get(path).status_code == 404


def test_seed_is_idempotent(app, db):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    assert count(db, Ingrediente) == 6 and count(db, Plato) == 2
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    assert count(db, Ingrediente) == 6
    assert all(i.cantidad == 0 for i in db.session.scalars(select(Ingrediente)))
