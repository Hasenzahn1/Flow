from flask import Blueprint, render_template, jsonify, request

from core.operation_overview.operation_db import get_operations, add_operation

bp = Blueprint('operation_overview', __name__)

@bp.route("/operation_overview")
def operation_overview():
    operations = get_operations()
    print(operations)
    return render_template("operation_selection.html", operations=operations)

@bp.route("/api/operation_overview", methods=["POST"])
def api_operation_overview_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or '').strip()

    if not name:
        return jsonify({'error': 'Please provide a name'}), 400
    
    new = add_operation(name)
    return jsonify(new), 201

def register(app):
    app.register_blueprint(bp)