import json
import os
import subprocess
import time
import sys
from datetime import datetime
from urllib.parse import urlsplit
from urllib.request import urlopen

from flask import Blueprint, render_template, jsonify, request

from core.auth import admin_required
from core.index_db import (
    add_tool,
    delete_tool,
    get_tool,
    get_tools,
    reorder_tools,
    update_tool,
)
from core.operation_overview.operation_db import get_operations

bp = Blueprint('index', __name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_upd_cache = {'ts': 0, 'available': False}
TOOL_ICON_KEYS = {"alert", "file", "grid", "monitor", "puzzle", "settings", "user-plus", "users"}
TOOL_COLORS = {"amber", "blue", "cyan", "green", "red", "violet"}
TOOL_FIELDS = {"label", "route", "icon_path", "description", "color", "active"}


def _is_external_route(route):
    return urlsplit(route).scheme in {"http", "https"}


def _validate_route(route):
    if any(ord(character) < 32 for character in route) or "\\" in route:
        return False
    if route.startswith("/") and not route.startswith("//"):
        return True
    parsed = urlsplit(route)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _tool_payload(payload, partial=False):
    if not isinstance(payload, dict):
        return None, "Ungültige Anfrage."

    unknown = set(payload) - TOOL_FIELDS
    if unknown:
        return None, "Die Anfrage enthält unbekannte Felder."

    values = {}
    if not partial or "label" in payload:
        label = payload.get("label")
        if not isinstance(label, str) or not label.strip():
            return None, "Bitte einen Titel angeben."
        values["label"] = label.strip()

    if not partial or "route" in payload:
        route = payload.get("route")
        if not isinstance(route, str) or not route.strip() or not _validate_route(route.strip()):
            return None, "Bitte eine gültige interne Route oder HTTP(S)-URL angeben."
        values["route"] = route.strip()

    if not partial or "description" in payload:
        description = payload.get("description")
        if description is not None and not isinstance(description, str):
            return None, "Die Beschreibung ist ungültig."
        values["description"] = (description.strip() or None) if isinstance(description, str) else None

    if not partial or "icon_path" in payload:
        icon_path = payload.get("icon_path", "grid")
        if icon_path not in TOOL_ICON_KEYS:
            return None, "Bitte ein gültiges Icon auswählen."
        values["icon_path"] = icon_path

    if not partial or "color" in payload:
        color = payload.get("color", "blue")
        if color not in TOOL_COLORS:
            return None, "Bitte eine gültige Kartenfarbe auswählen."
        values["color"] = color

    if not partial or "active" in payload:
        active = payload.get("active", True)
        if type(active) is bool:
            values["active"] = int(active)
        elif type(active) is int and active in (0, 1):
            values["active"] = active
        else:
            return None, "Der Aktiv-Status ist ungültig."

    if partial and not values:
        return None, "Keine Änderungen angegeben."
    return values, None


def _tools_for_view(tools):
    result = []
    for tool in tools:
        if not _validate_route(tool.get("route") or ""):
            continue
        item = dict(tool)
        item["icon_path"] = item.get("icon_path") if item.get("icon_path") in TOOL_ICON_KEYS else "grid"
        item["color"] = item.get("color") if item.get("color") in TOOL_COLORS else "blue"
        item["is_external"] = _is_external_route(item["route"])
        result.append(item)
    return result


@bp.route('/')
def index():
    operations = get_operations()
    active_tools = _tools_for_view(get_tools(only_active=True))
    recent_activity = []
    for operation in operations[:5]:
        date = datetime.fromtimestamp(operation['date'])
        recent_activity.append({
            'name': operation['name'],
            'meta': f"Lage · {date:%d.%m.%Y, %H:%M} Uhr",
            'href': f"/operation_overview/{operation['id']}",
            'tone': 'red',
        })
    return render_template(
        "index.html",
        operation_count=len(operations),
        recent_activity=recent_activity,
        tool_count=len(active_tools),
    )


@bp.route('/tools')
def tools_page():
    return render_template("tools.html", tools=_tools_for_view(get_tools(only_active=True)))

@bp.route("/api/tools", methods=['GET'])
@admin_required
def api_tools_list():
    tools = get_tools(only_active=False)
    return jsonify(tools)

@bp.route("/api/tools", methods=['POST'])
@admin_required
def api_tool_create():
    values, error = _tool_payload(request.get_json(silent=True), partial=False)
    if error:
        return jsonify({'error': error}), 400
    new = add_tool(
        values["label"],
        values["route"],
        icon=values["icon_path"],
        description=values["description"],
        color=values["color"],
        active=values["active"],
    )
    return jsonify(new), 201


@bp.route("/api/tools/order", methods=['PUT'])
@admin_required
def api_tools_order():
    data = request.get_json(silent=True)
    tool_ids = data.get("tool_ids") if isinstance(data, dict) else None
    if (
        not isinstance(tool_ids, list)
        or any(type(tool_id) is not int for tool_id in tool_ids)
        or len(tool_ids) != len(set(tool_ids))
        or not reorder_tools(tool_ids)
    ):
        return jsonify({'error': 'Die übermittelte Reihenfolge ist ungültig.'}), 400
    return jsonify(get_tools(only_active=False))

@bp.route("/api/tools/<int:tool_id>", methods=['PUT'])
@admin_required
def api_tool_update(tool_id):
    if get_tool(tool_id) is None:
        return jsonify({'error': 'Tool nicht gefunden.'}), 404

    values, error = _tool_payload(request.get_json(silent=True), partial=True)
    if error:
        return jsonify({'error': error}), 400
    changed = update_tool(tool_id, **values)
    return jsonify(changed), 200

@bp.route("/api/tools/<int:tool_id>", methods=['DELETE'])
@admin_required
def api_tool_delete(tool_id):
    if not delete_tool(tool_id):
        return jsonify({'error': 'Tool nicht gefunden.'}), 404
    return '', 204


@bp.route('/api/update/check')
@admin_required
def api_update_check():
    now = time.time()
    if now - _upd_cache['ts'] < 600:
        return jsonify({'available': _upd_cache['available']})
    try:
        local = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=_ROOT).decode().strip()
        with urlopen('https://api.github.com/repos/Hasenzahn1/Flow/commits/master', timeout=5) as r:
            remote = json.loads(r.read())['sha']
        _upd_cache['available'] = local != remote
    except Exception:
        _upd_cache['available'] = False
    _upd_cache['ts'] = now
    return jsonify({'available': _upd_cache['available']})


@bp.route('/api/update/apply', methods=['POST'])
@admin_required
def api_update_apply():
    if sys.platform == 'win32':
        script = os.path.join(_ROOT, 'update.bat')
        subprocess.Popen([script, str(os.getpid())], creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        script = os.path.join(_ROOT, 'update.sh')
        subprocess.Popen(['bash', script, str(os.getpid())])
    return jsonify({'ok': True})


def register(app):
    app.register_blueprint(bp)
