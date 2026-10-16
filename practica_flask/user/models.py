"""Local accounts; passwords are stored only as secure hashes."""

from typing import TYPE_CHECKING

from flask_login import UserMixin

if TYPE_CHECKING:
    from practica_flask.inventory.models import MovimientoInventario
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from practica_flask.extensions import db


class User(UserMixin, db.Model):
    """An account with a unique username and a hashed password."""

    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    movimientos: Mapped[list["MovimientoInventario"]] = relationship(
        back_populates="usuario"
    )

    def set_password(self, password):
        """Hash a new password before storing it."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify a password against the stored hash."""
        return check_password_hash(self.password_hash, password)
