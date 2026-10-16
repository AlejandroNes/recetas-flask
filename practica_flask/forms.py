"""Shared Spanish translations for all WTForms validation messages."""

from functools import lru_cache

from flask_wtf import FlaskForm
from wtforms.i18n import get_translations


@lru_cache(maxsize=1)
def spanish_translations():
    """Load the translations bundled with WTForms once."""
    return get_translations(["es"])


class SpanishForm(FlaskForm):
    """A CSRF-protected form with Spanish field validation."""

    class Meta(FlaskForm.Meta):
        """Keep Flask-WTF session integration and set the display language."""

        def get_translations(self, form):
            """Translate built-in required, range and length validators."""
            return spanish_translations()
