from flask import Blueprint, render_template

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/sobre")
def sobre():
    return render_template("pages/landing.html")
