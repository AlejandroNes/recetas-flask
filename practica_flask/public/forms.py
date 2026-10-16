"""Minimal username/password authentication."""

from wtforms import PasswordField, StringField
from wtforms.validators import EqualTo, InputRequired, Length, Regexp

from practica_flask.forms import SpanishForm


class LoginForm(SpanishForm):
    """Validate the credentials submitted for a login attempt."""

    username = StringField("Usuario", validators=[InputRequired(), Length(max=40)])
    password = PasswordField(
        "Contraseña", validators=[InputRequired(), Length(max=128)]
    )


class RegisterForm(LoginForm):
    """Validate a new username and matching passwords."""

    username = StringField(
        "Usuario",
        validators=[
            InputRequired(),
            Length(min=3, max=40),
            Regexp(
                r"^[a-zA-Z0-9_]+$",
                message="Usa letras sin acentos, números o guion bajo.",
            ),
        ],
    )
    password = PasswordField(
        "Contraseña",
        validators=[
            InputRequired(),
            Length(min=8, max=128, message="Usa entre 8 y 128 caracteres."),
        ],
    )
    confirm = PasswordField(
        "Repetir contraseña",
        validators=[
            InputRequired(),
            EqualTo("password", message="Las contraseñas no coinciden."),
        ],
    )
