"""Compatibility redirect for the original template's member page."""

from flask import Blueprint, redirect, url_for
from flask_login import login_required

blueprint = Blueprint("user", __name__, url_prefix="/users")


@blueprint.route("/members/")
@login_required
def members():
    """Redirect the former member page to the kitchen overview."""
    return redirect(url_for("inventory.dashboard"))
