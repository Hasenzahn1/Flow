from flask import Blueprint, render_template, jsonify, request

from pages.index_db import get_tools, add_tool, get_tool, update_tool, delete_tool

bp = Blueprint('index', __name__)


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


def register(app):
    app.register_blueprint(bp)