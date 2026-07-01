import json
import os
import subprocess
import time
import sys
from urllib.request import urlopen

from flask import Blueprint, render_template, jsonify, request

from core.index_db import get_tools, add_tool, get_tool, update_tool, delete_tool

bp = Blueprint('index', __name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_upd_cache = {'ts': 0, 'available': False}


@bp.route('/')
def index():
    tools = get_tools(only_active=True)
    return render_template("index.html", tools=tools)

@bp.route("/api/tools", methods=['GET'])
def api_tools_list():
    tools = get_tools(only_active=False)
    return jsonify(tools)

@bp.route("/api/tools", methods=['POST'])
def api_tool_create():
    data = request.get_json(silent=True) or {}
    label = (data.get('label') or '').strip()
    route = (data.get('route') or '').strip()

    if not label or not route:
        return jsonify({'error': 'Please provide a label and a route'}), 400

    new = add_tool(label, route)
    return jsonify(new), 201

@bp.route("/api/tools/<int:tool_id>", methods=['PUT'])
def api_tool_update(tool_id):
    if get_tool(tool_id) is None: return jsonify({'error': 'Tool not found'}), 404

    data = request.get_json(silent=True) or {}
    changed = update_tool(tool_id, **data)
    return jsonify(changed), 200

@bp.route("/api/tools/<int:tool_id>", methods=['DELETE'])
def api_tool_delete(tool_id):
    if not delete_tool(tool_id): return jsonify({'error': 'Tool not found'}), 404
    return jsonify({'ok': True}), 404


@bp.route('/api/update/check')
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