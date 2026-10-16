"""Isolated SQLite fixtures; application data is never touched by tests."""

from decimal import Decimal

import pytest

from practica_flask.app import create_app
from practica_flask.extensions import db as database
from practica_flask.inventory.models import Categoria, Ingrediente, Plato, Receta
from practica_flask.user.models import User


@pytest.fixture
def app():
    app = create_app("tests.settings")
    with app.app_context():
        database.create_all()
        yield app
        database.session.remove()
        database.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return database


@pytest.fixture
def user(db):
    user = User(username="cocinero")
    user.set_password("secreto123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def auth(client, user):
    response = client.post(
        "/login/", data={"username": user.username, "password": "secreto123"}
    )
    assert response.status_code == 302
    return client


@pytest.fixture
def catalog(db):
    cat = Categoria(nombre="Verduras", descripcion="Frescas")
    first = Ingrediente(
        nombre="Tomate",
        categoria=cat,
        unidad_medida="kg",
        cantidad=Decimal("5"),
        costo_unitario=Decimal("8"),
        stock_minimo=Decimal("2"),
    )
    second = Ingrediente(
        nombre="Cebolla",
        categoria=cat,
        unidad_medida="kg",
        cantidad=Decimal("1"),
        costo_unitario=Decimal("6"),
        stock_minimo=Decimal("1"),
    )
    dish = Plato(nombre="Ensalada", descripcion="Fresca", precio=Decimal("20"))
    dish.recetas = [
        Receta(ingrediente=first, cantidad_necesaria=Decimal(".200")),
        Receta(ingrediente=second, cantidad_necesaria=Decimal(".100")),
    ]
    db.session.add_all([cat, first, second, dish])
    db.session.commit()
    return cat, first, second, dish
