"""Database constraints and real Alembic upgrades from an empty SQLite file."""

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from practica_flask.inventory.models import Ingrediente, Receta


def test_six_tables_and_foreign_keys(db):
    assert set(inspect(db.engine).get_table_names()) == {
        "usuarios",
        "categorias",
        "ingredientes",
        "platos",
        "recetas",
        "movimientos_inventario",
    }
    assert db.session.scalar(text("PRAGMA foreign_keys")) == 1
    db.session.add(
        Ingrediente(
            nombre="Huérfano",
            categoria_id=999,
            unidad_medida="kg",
            cantidad=0,
            costo_unitario=1,
            stock_minimo=0,
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_negative_stock_constraint(catalog, db):
    catalog[1].cantidad = Decimal("-1")
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_duplicate_recipe_constraint(catalog, db):
    db.session.add(
        Receta(
            plato_id=catalog[3].id, ingrediente_id=catalog[1].id, cantidad_necesaria=1
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_migrations_on_fresh_database(tmp_path):
    env = dict(os.environ, DATABASE_URL=f'sqlite:///{tmp_path / "migration.db"}')
    root = Path(__file__).resolve().parents[1]
    for args in [("db", "upgrade"), ("db", "check")]:
        result = subprocess.run(
            [sys.executable, "-m", "flask", *args],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
