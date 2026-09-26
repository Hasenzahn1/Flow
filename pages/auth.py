from flask import Blueprint, jsonify, render_template, request

from core.auth import (
    activate_admin,
    activate_guest,
    admin_required,
    change_admin_password,
    current_role,
    uses_default_password,
    verify_admin_password,
)


bp = Blueprint("auth", __name__)


@bp.post("/api/auth/admin")
def api_activate_admin():
    payload = request.get_json(silent=True) or {}
    password = payload.get("password")
    if not isinstance(password, str) or not password:
        return jsonify({"error": "Bitte das Admin-Passwort eingeben."}), 400
    if not activate_admin(password):
        return jsonify({"error": "Das Admin-Passwort ist nicht korrekt."}), 401
    return jsonify({"role": "admin", "display_name": "Admin", "is_admin": True})


@bp.post("/api/auth/guest")
def api_activate_guest():
    activate_guest()
    return jsonify({"role": "guest", "display_name": "Guest", "is_admin": False})


@bp.get("/settings")
@admin_required
def settings():
    return render_template("settings.html", uses_default_password=uses_default_password())


@bp.put("/api/settings/admin-password")
@admin_required
def api_change_admin_password():
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password")
    new_password = payload.get("new_password")
    confirmation = payload.get("confirmation")

    if not all(isinstance(value, str) for value in (current_password, new_password, confirmation)):
        return jsonify({"error": "Bitte alle Passwortfelder ausfüllen."}), 400
    if not verify_admin_password(current_password):
        return jsonify({"error": "Das aktuelle Passwort ist nicht korrekt."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Das neue Passwort muss mindestens 8 Zeichen lang sein."}), 400
    if new_password != confirmation:
        return jsonify({"error": "Die neuen Passwörter stimmen nicht überein."}), 400

    change_admin_password(new_password)
    return jsonify({"ok": True, "message": "Admin-Passwort wurde geändert."})


def _validate_auth_session():
    current_role()


def _inject_auth_context():
    role = current_role()
    return {
        "current_role": role,
        "is_admin": role == "admin",
    }


def register(app):
    app.register_blueprint(bp)
    app.before_request(_validate_auth_session)
    app.context_processor(_inject_auth_context)
