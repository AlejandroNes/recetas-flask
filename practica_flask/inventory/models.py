"""Typed SQLAlchemy mappings based on the supplied diagram."""

from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from practica_flask.extensions import db
from practica_flask.user.models import User


def local_today():
    """Return the business date in Bolivia."""
    return datetime.now(ZoneInfo("America/La_Paz")).date()


class Categoria(db.Model):
    """An optional active grouping for ingredients."""

    __tablename__ = "categorias"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    activo: Mapped[bool] = mapped_column(default=True)
    ingredientes: Mapped[list["Ingrediente"]] = relationship(back_populates="categoria")


class Ingrediente(db.Model):
    """Stock, unit cost and expiry date of a kitchen ingredient."""

    __tablename__ = "ingredientes"
    __table_args__ = (
        CheckConstraint("cantidad >= 0", name="ck_ingrediente_cantidad"),
        CheckConstraint("costo_unitario >= 0", name="ck_ingrediente_costo"),
        CheckConstraint("stock_minimo >= 0", name="ck_ingrediente_minimo"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), index=True)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    unidad_medida: Mapped[str] = mapped_column(String(20))
    costo_unitario: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0")
    )
    stock_minimo: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    fecha_vencimiento: Mapped[date | None]
    activo: Mapped[bool] = mapped_column(default=True)
    categoria: Mapped[Categoria] = relationship(back_populates="ingredientes")
    recetas: Mapped[list["Receta"]] = relationship(back_populates="ingrediente")
    movimientos: Mapped[list["MovimientoInventario"]] = relationship(
        back_populates="ingrediente"
    )

    @property
    def vencido(self):
        """Report whether the ingredient expired before today."""
        return (
            self.fecha_vencimiento is not None
            and self.fecha_vencimiento < local_today()
        )

    @property
    def disponible(self):
        """Report whether the ingredient can be used for cooking."""
        return self.activo and self.categoria.activo and not self.vencido


class Plato(db.Model):
    """A dish with a selling price and ingredients per portion."""

    __tablename__ = "platos"
    __table_args__ = (CheckConstraint("precio >= 0", name="ck_plato_precio"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(500))
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    activo: Mapped[bool] = mapped_column(default=True)
    recetas: Mapped[list["Receta"]] = relationship(
        back_populates="plato", cascade="all, delete-orphan"
    )

    @property
    def costo(self):
        """Calculate ingredient cost per portion using exact decimals."""
        return sum(
            (r.cantidad_necesaria * r.ingrediente.costo_unitario for r in self.recetas),
            Decimal("0"),
        )


class Receta(db.Model):
    """One ingredient and its required amount for one dish portion."""

    __tablename__ = "recetas"
    __table_args__ = (
        UniqueConstraint("plato_id", "ingrediente_id", name="uq_receta_ingrediente"),
        CheckConstraint("cantidad_necesaria > 0", name="ck_receta_cantidad"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plato_id: Mapped[int] = mapped_column(ForeignKey("platos.id"), index=True)
    ingrediente_id: Mapped[int] = mapped_column(
        ForeignKey("ingredientes.id"), index=True
    )
    cantidad_necesaria: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    plato: Mapped[Plato] = relationship(back_populates="recetas")
    ingrediente: Mapped[Ingrediente] = relationship(back_populates="recetas")


class MovimientoInventario(db.Model):
    """An immutable stock movement attributed to its operator."""

    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        CheckConstraint("tipo IN ('entrada', 'salida')", name="ck_movimiento_tipo"),
        CheckConstraint("cantidad > 0", name="ck_movimiento_cantidad"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ingrediente_id: Mapped[int] = mapped_column(
        ForeignKey("ingredientes.id"), index=True
    )
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    motivo: Mapped[str] = mapped_column(String(250))
    fecha: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    ingrediente: Mapped[Ingrediente] = relationship(back_populates="movimientos")
    usuario: Mapped[User] = relationship(back_populates="movimientos")
