"""Validated forms with exact decimal quantities."""

from decimal import Decimal

from wtforms import (
    DateField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import (
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from practica_flask.forms import SpanishForm


def precision(places):
    """Build a validator that rejects unsupported decimal precision."""

    def validate(form, field):
        """Validate the number of fractional digits."""
        if field.data is not None and (
            not field.data.is_finite()
            or abs(field.data) >= Decimal("1e12")
            or field.data != field.data.quantize(Decimal(10) ** -places)
        ):
            raise ValidationError(f"Usa como máximo {places} decimales.")

    return validate


class SafeDecimalField(DecimalField):
    """Reject non-finite decimal input before range validation."""

    def process_formdata(self, valuelist):
        """Parse a finite decimal from the submitted form field."""
        super().process_formdata(valuelist)
        if self.data is not None and not self.data.is_finite():
            self.data = None
            raise ValueError("Introduce un número finito.")


def quantity(label, positive=False):
    """Build a bounded three-decimal quantity input."""
    return SafeDecimalField(
        label,
        places=None,
        validators=[
            InputRequired(),
            NumberRange(
                min=Decimal(".001") if positive else 0, max=Decimal("999999999.999")
            ),
            precision(3),
        ],
        render_kw={"step": "0.001", "min": "0.001" if positive else "0"},
    )


def money(label):
    """Build a bounded two-decimal monetary input."""
    return SafeDecimalField(
        label,
        places=None,
        validators=[
            InputRequired(),
            NumberRange(min=0, max=Decimal("9999999999.99")),
            precision(2),
        ],
        render_kw={"step": "0.01", "min": "0"},
    )


class CategoriaForm(SpanishForm):
    """Create or edit a category."""

    nombre = StringField(
        "Nombre",
        filters=[lambda v: v.strip() if v else v],
        validators=[InputRequired(), Length(min=1, max=100)],
    )
    descripcion = TextAreaField("Descripción", validators=[Optional(), Length(max=250)])


class IngredienteForm(SpanishForm):
    """Edit ingredient metadata without changing its stock directly."""

    nombre = StringField(
        "Nombre",
        filters=[lambda v: v.strip() if v else v],
        validators=[InputRequired(), Length(min=1, max=120)],
    )
    categoria_id = SelectField("Categoría", coerce=int, validators=[InputRequired()])
    unidad_medida = SelectField(
        "Unidad de medida",
        choices=[
            ("kg", "Kilogramos (kg)"),
            ("g", "Gramos (g)"),
            ("l", "Litros (l)"),
            ("ml", "Mililitros (ml)"),
            ("unidad", "Unidades"),
        ],
    )
    costo_unitario = money("Costo por unidad (Bs)")
    stock_minimo = quantity("Stock mínimo")
    fecha_vencimiento = DateField("Fecha de vencimiento", validators=[Optional()])


class PlatoForm(SpanishForm):
    """Create or edit a dish and its selling price."""

    nombre = StringField(
        "Nombre del plato",
        filters=[lambda v: v.strip() if v else v],
        validators=[InputRequired(), Length(min=1, max=120)],
    )
    descripcion = TextAreaField("Descripción", validators=[Optional(), Length(max=500)])
    precio = money("Precio de venta (Bs)")


class RecetaForm(SpanishForm):
    """Choose an ingredient and its quantity per portion."""

    ingrediente_id = SelectField(
        "Ingrediente", coerce=int, validators=[InputRequired()]
    )
    cantidad_necesaria = quantity("Cantidad para una porción", positive=True)


class MovimientoForm(SpanishForm):
    """Record an incoming or outgoing stock movement."""

    ingrediente_id = SelectField(
        "Ingrediente", coerce=int, validators=[InputRequired()]
    )
    tipo = SelectField(
        "Tipo de movimiento",
        choices=[("entrada", "Entrada de stock"), ("salida", "Salida de stock")],
    )
    cantidad = quantity("Cantidad", positive=True)
    motivo = StringField(
        "Motivo",
        filters=[lambda v: v.strip() if v else v],
        validators=[InputRequired(), Length(min=3, max=250)],
    )


class PreparacionForm(SpanishForm):
    """Request a bounded integer number of dish portions."""

    porciones = IntegerField(
        "Porciones a preparar",
        default=1,
        validators=[InputRequired(), NumberRange(min=1, max=1000)],
    )


class ActionForm(SpanishForm):
    """CSRF token for action buttons."""
