from functools import wraps

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.db import get_db


ROLE_GUEST = "guest"
ROLE_ADMIN = "admin"


def get_auth_settings():
    con = get_db()
    row = con.execute(
        "SELECT admin_password_hash, session_version FROM auth_settings WHERE id = 1"
    ).fetchone()
    con.close()
    if row is None:
        raise RuntimeError("Auth-Konfiguration fehlt. Bitte Datenbankmigration ausführen.")
    return dict(row)


def current_role():
    if session.get("role") != ROLE_ADMIN:
        return ROLE_GUEST

    settings = get_auth_settings()
    if session.get("auth_version") != settings["session_version"]:
        session.clear()
        return ROLE_GUEST
    return ROLE_ADMIN


def is_admin():
    return current_role() == ROLE_ADMIN


def verify_admin_password(password):
    if not isinstance(password, str):
        return False
    return check_password_hash(get_auth_settings()["admin_password_hash"], password)


def activate_admin(password):
    if not verify_admin_password(password):
        return False
    settings = get_auth_settings()
    session.clear()
    session.permanent = False
    session["role"] = ROLE_ADMIN
    session["auth_version"] = settings["session_version"]
    return True


def activate_guest():
    session.clear()
    session.permanent = False


def change_admin_password(new_password):
    password_hash = generate_password_hash(new_password)
    con = get_db()
    con.execute(
        """
        UPDATE auth_settings
        SET admin_password_hash = ?, session_version = session_version + 1
        WHERE id = 1
        """,
        (password_hash,),
    )
    con.commit()
    version = con.execute(
        "SELECT session_version FROM auth_settings WHERE id = 1"
    ).fetchone()["session_version"]
    con.close()
    session["role"] = ROLE_ADMIN
    session["auth_version"] = version


def uses_default_password():
    return verify_admin_password("admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_admin():
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": "Admin-Rechte erforderlich."}), 403
        return redirect(url_for("index.index"))

    return wrapped
