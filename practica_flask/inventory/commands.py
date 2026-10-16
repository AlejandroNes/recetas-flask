"""Optional, idempotent sample catalog without accounts or invented movements."""

from decimal import Decimal

import click
from flask.cli import with_appcontext
from sqlalchemy import select

from practica_flask.extensions import db

from .models import Categoria, Ingrediente, Plato, Receta


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Create an illustrative catalog only when inventory is empty."""
    if (
        db.session.scalar(select(Categoria.id).limit(1)) is not None
        or db.session.scalar(select(Plato.id).limit(1)) is not None
    ):
        click.echo("Ya existe un catálogo. No se cambiaron datos.")
        return
    verduras = Categoria(
        nombre="Verduras", descripcion="Productos frescos de la huerta"
    )
    secos = Categoria(
        nombre="Granos y despensa", descripcion="Bases para los platos de cada día"
    )
    lacteos = Categoria(nombre="Lácteos", descripcion="Leche, quesos y derivados")
    ingredients = [
        Ingrediente(
            nombre="Tomate",
            categoria=verduras,
            unidad_medida="kg",
            costo_unitario=8,
            stock_minimo=2,
        ),
        Ingrediente(
            nombre="Zanahoria",
            categoria=verduras,
            unidad_medida="kg",
            costo_unitario=6,
            stock_minimo=1,
        ),
        Ingrediente(
            nombre="Cebolla",
            categoria=verduras,
            unidad_medida="kg",
            costo_unitario=7,
            stock_minimo=1,
        ),
        Ingrediente(
            nombre="Quinua",
            categoria=secos,
            unidad_medida="kg",
            costo_unitario=24,
            stock_minimo=2,
        ),
        Ingrediente(
            nombre="Arroz",
            categoria=secos,
            unidad_medida="kg",
            costo_unitario=10,
            stock_minimo=3,
        ),
        Ingrediente(
            nombre="Queso fresco",
            categoria=lacteos,
            unidad_medida="kg",
            costo_unitario=38,
            stock_minimo=1,
        ),
    ]
    bowl = Plato(
        nombre="Bowl de quinua y huerta",
        descripcion="Quinua con tomate y queso fresco.",
        precio=28,
    )
    arroz = Plato(
        nombre="Arroz de la casa",
        descripcion="Arroz con zanahoria y cebolla.",
        precio=20,
    )
    db.session.add_all([verduras, secos, lacteos, *ingredients, bowl, arroz])
    db.session.flush()
    for plato, index, quantity in [
        (bowl, 3, ".100"),
        (bowl, 0, ".080"),
        (bowl, 5, ".040"),
        (arroz, 4, ".120"),
        (arroz, 1, ".060"),
        (arroz, 2, ".030"),
    ]:

        db.session.add(
            Receta(
                plato=plato,
                ingrediente=ingredients[index],
                cantidad_necesaria=Decimal(quantity),
            )
        )
    db.session.commit()
    click.echo(
        "Catálogo ilustrativo creado: 3 categorías, 6 ingredientes y 2 recetas. "
        "Stock inicial: cero. No se crearon usuarios."
    )
