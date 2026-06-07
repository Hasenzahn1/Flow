from flask import Blueprint, render_template, jsonify, request
from flask_socketio import join_room, emit

from core.operation_overview.operation_db import get_operations, add_operation, get_operation
from core.operation_overview.mission_db import get_missions, update_mission, add_mission
from core.operation_overview.person_db import get_persons, update_person, add_person

bp = Blueprint('operation_overview', __name__)


def register_socket_events(socketio):
    @socketio.on('join')
    def on_join(data):
        join_room(f"operation_{data['operation_id']}")

    @socketio.on('update_mission')
    def on_update_mission(data):
        mission_id = data['mission_id']
        field = data['field']
        value = data['value']
        updated = update_mission(mission_id, **{field: value})
        emit('mission_updated', updated, room=f"operation_{updated['operation_id']}")

    @socketio.on('update_person')
    def on_update_person(data):
        person_id = data['person_id']
        field = data['field']
        value = data['value']
        updated = update_person(person_id, **{field: value})
        emit('person_updated', updated, room=f"operation_{data['operation_id']}")

    @socketio.on('add_mission')
    def on_add_mission(data):
        operation_id = data['operation_id']
        new_mission = add_mission(operation_id, '', '', '')
        new_mission['persons'] = []
        emit('mission_added', new_mission, room=f"operation_{operation_id}")

    @socketio.on('add_person')
    def on_add_person(data):
        mission_id = data['mission_id']
        operation_id = data['operation_id']
        new_person = add_person(mission_id, '', '', None, '', '', '')
        emit('person_added', {'mission_id': mission_id, 'person': new_person}, room=f"operation_{operation_id}")

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

@bp.route("/operation_overview/<int:operation_id>")
def operation_overview_list(operation_id):
    operation = get_operation(operation_id)
    missions = get_missions(operation_id)
    for mission in missions:
        mission["persons"] = get_persons(mission["id"])
    
    operation["missions"] = missions
    
    return render_template("operation_edit.html", operation=operation)

def register(app, socketio):
    app.register_blueprint(bp)
    register_socket_events(socketio)