import datetime
import os
import re
import zipfile
from io import BytesIO

from flask import Blueprint, abort, render_template, jsonify, request, send_file
from flask_socketio import join_room, emit

from core.operation_overview.operation_db import get_operations, add_operation, get_operation
from core.operation_overview.mission_db import get_missions, update_mission, add_mission, delete_mission
from core.operation_overview.person_db import get_persons, update_person, add_person, delete_person
from core.operation_overview.pdf_export import (
    SECTION_HELPERS_DETAIL,
    SECTION_HELPERS_SUMMARY,
    SECTION_ORDER,
    SECTION_PATIENTS,
    SECTION_VEHICLES,
    generate_operation_pdf,
)
from core.operation_overview.helper_parser import HelperPayloadError, parse_helper_payload
from core.operation_overview.helper_db import (
    create_or_merge,
    delete_helper,
    find_duplicate,
    get_conflicts,
    get_helper,
    list_helpers,
    normalize_helper_data,
    update_helper,
)
from core.operation_overview.vehicle_db import (
    VehiclePayloadError,
    assign_helper,
    count_vehicles,
    create_vehicle,
    delete_vehicle,
    get_vehicle,
    list_vehicles,
    reorder_vehicles,
    update_vehicle,
)
from core.operation_overview.vehicle_templates import (
    VehicleTemplateError,
    apply_template,
    delete_template,
    get_template,
    list_templates,
    save_template,
)

bp = Blueprint('operation_overview', __name__)
_socketio = None


def _helper_error(message, status=400):
    return jsonify({'error': str(message)}), status


def _emit_helper_event(event, operation_id, helper=None, helper_id=None):
    if _socketio is None:
        return
    payload = {'operation_id': operation_id}
    if helper is not None:
        payload['helper'] = helper
    if helper_id is not None:
        payload['helper_id'] = helper_id
    _socketio.emit(event, payload, to=f"operation_{operation_id}")


def _vehicle_error(message, status=400):
    return jsonify({'error': str(message)}), status


def _emit_vehicles_changed(operation_id):
    if _socketio is not None:
        _socketio.emit(
            'vehicles_changed', {'operation_id': operation_id},
            to=f"operation_{operation_id}",
        )


def _emit_templates_changed():
    if _socketio is not None:
        _socketio.emit('vehicle_templates_changed', {})


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

    @socketio.on('delete_mission')
    def on_delete_mission(data):
        mission_id = data['mission_id']
        operation_id = data['operation_id']
        if delete_mission(mission_id):
            emit('mission_deleted', {'mission_id': mission_id}, room=f"operation_{operation_id}")

    @socketio.on('delete_person')
    def on_delete_person(data):
        person_id = data['person_id']
        mission_id = data['mission_id']
        operation_id = data['operation_id']
        if delete_person(person_id):
            emit('person_deleted', {'person_id': person_id, 'mission_id': mission_id}, room=f"operation_{operation_id}")

@bp.route("/operation_overview")
def operation_overview():
    operations = get_operations()
    for operation in operations:
        missions = get_missions(operation['id'])
        operation['participant_count'] = sum(
            len(get_persons(mission['id'])) for mission in missions
        )
        operation['status'] = 'Aktiv'
    return render_template("operation_overview.html", operations=operations)

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
    if operation is None:
        abort(404)

    missions = get_missions(operation_id)
    operation["participant_count"] = sum(
        len(get_persons(mission["id"])) for mission in missions
    )
    operation["vehicle_count"] = count_vehicles(operation_id)
    return render_template("operation_tools.html", operation=operation)

@bp.route("/operation_overview/<int:operation_id>/patients")
def operation_patients(operation_id):
    operation = get_operation(operation_id)
    if operation is None:
        abort(404)

    missions = get_missions(operation_id)
    for mission in missions:
        mission["persons"] = get_persons(mission["id"])
    operation["missions"] = missions
    return render_template("operation_edit.html", operation=operation)


@bp.route("/operation_overview/<int:operation_id>/helpers")
def operation_helpers(operation_id):
    operation = get_operation(operation_id)
    if operation is None:
        abort(404)
    return render_template("helpers.html", operation=operation)


@bp.route("/operation_overview/<int:operation_id>/vehicles")
def operation_vehicles(operation_id):
    operation = get_operation(operation_id)
    if operation is None:
        abort(404)
    return render_template("vehicles.html", operation=operation)


@bp.route("/api/operation_overview/<int:operation_id>/helpers", methods=["GET"])
def api_helpers_list(operation_id):
    if get_operation(operation_id) is None:
        return _helper_error("Lage nicht gefunden.", 404)
    result = list_helpers(
        operation_id,
        q=request.args.get("q", ""),
        vehicle=request.args.get("vehicle", ""),
        qualification=request.args.get("qualification", ""),
        nutrition=request.args.get("nutrition", ""),
        status=request.args.get("status", ""),
    )
    return jsonify(result)


@bp.route("/api/operation_overview/<int:operation_id>/helpers/preview", methods=["POST"])
def api_helpers_preview(operation_id):
    if get_operation(operation_id) is None:
        return _helper_error("Lage nicht gefunden.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        parsed = parse_helper_payload(payload.get("raw_payload"))
        existing = find_duplicate(operation_id, parsed["data"])
        conflicts = get_conflicts(existing, parsed["data"])
    except HelperPayloadError as exc:
        return _helper_error(exc)
    return jsonify({
        "source": parsed["source"],
        "data": parsed["data"],
        "duplicate": existing,
        "conflicts": conflicts,
        "message": "Bereits erfasste Person gefunden – Daten ergänzt" if existing else "QR-Code erfolgreich erkannt",
    })


@bp.route("/api/operation_overview/<int:operation_id>/helpers", methods=["POST"])
def api_helpers_create(operation_id):
    if get_operation(operation_id) is None:
        return _helper_error("Lage nicht gefunden.", 404)
    payload = request.get_json(silent=True) or {}
    raw_payload = payload.get("raw_payload")
    try:
        source = parse_helper_payload(raw_payload)["source"] if raw_payload else "Manuell"
        helper, merged, complemented, conflicts = create_or_merge(
            operation_id, payload.get("data") or {}, source
        )
    except HelperPayloadError as exc:
        return _helper_error(exc)
    _emit_helper_event("helper_saved", operation_id, helper=helper)
    _emit_vehicles_changed(operation_id)
    return jsonify({
        "helper": helper,
        "merged": merged,
        "complemented_fields": complemented,
        "conflicts": conflicts,
        "message": "Bereits erfasste Person gefunden – Daten ergänzt" if merged else "Helfer erfolgreich erfasst",
    }), 200 if merged else 201


@bp.route("/api/operation_overview/<int:operation_id>/helpers/<int:helper_id>", methods=["PATCH"])
def api_helpers_update(operation_id, helper_id):
    if get_operation(operation_id) is None:
        return _helper_error("Lage nicht gefunden.", 404)
    payload = request.get_json(silent=True) or {}
    try:
        helper = update_helper(operation_id, helper_id, payload)
    except HelperPayloadError as exc:
        return _helper_error(exc)
    if helper is None:
        return _helper_error("Helfer nicht gefunden.", 404)
    _emit_helper_event("helper_saved", operation_id, helper=helper)
    _emit_vehicles_changed(operation_id)
    return jsonify(helper)


@bp.route("/api/operation_overview/<int:operation_id>/helpers/<int:helper_id>", methods=["DELETE"])
def api_helpers_delete(operation_id, helper_id):
    if get_operation(operation_id) is None:
        return _helper_error("Lage nicht gefunden.", 404)
    if not delete_helper(operation_id, helper_id):
        return _helper_error("Helfer nicht gefunden.", 404)
    _emit_helper_event("helper_deleted", operation_id, helper_id=helper_id)
    _emit_vehicles_changed(operation_id)
    return '', 204


@bp.route("/api/operation_overview/<int:operation_id>/vehicles", methods=["GET"])
def api_vehicles_list(operation_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    result = list_vehicles(operation_id)
    result["template_count"] = sum(1 for item in list_templates() if not item.get("invalid"))
    return jsonify(result)


@bp.route("/api/operation_overview/<int:operation_id>/vehicles", methods=["POST"])
def api_vehicles_create(operation_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    try:
        vehicle = create_vehicle(operation_id, request.get_json(silent=True))
    except VehiclePayloadError as exc:
        return _vehicle_error(exc)
    _emit_vehicles_changed(operation_id)
    return jsonify(vehicle), 201


@bp.route("/api/operation_overview/<int:operation_id>/vehicles/<int:vehicle_id>", methods=["PATCH"])
def api_vehicles_update(operation_id, vehicle_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    try:
        vehicle = update_vehicle(operation_id, vehicle_id, request.get_json(silent=True))
    except VehiclePayloadError as exc:
        return _vehicle_error(exc)
    if vehicle is None:
        return _vehicle_error("Fahrzeug nicht gefunden.", 404)
    _emit_vehicles_changed(operation_id)
    return jsonify(vehicle)


@bp.route("/api/operation_overview/<int:operation_id>/vehicles/<int:vehicle_id>", methods=["DELETE"])
def api_vehicles_delete(operation_id, vehicle_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    if not delete_vehicle(operation_id, vehicle_id):
        return _vehicle_error("Fahrzeug nicht gefunden.", 404)
    _emit_vehicles_changed(operation_id)
    _emit_helper_event("helper_saved", operation_id)
    return '', 204


@bp.route("/api/operation_overview/<int:operation_id>/vehicles/order", methods=["PUT"])
def api_vehicles_order(operation_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    payload = request.get_json(silent=True)
    vehicle_ids = payload.get("vehicle_ids") if isinstance(payload, dict) else None
    if not reorder_vehicles(operation_id, vehicle_ids):
        return _vehicle_error("Die Fahrzeugreihenfolge ist ungültig.")
    _emit_vehicles_changed(operation_id)
    return jsonify(list_vehicles(operation_id)["items"])


@bp.route("/api/operation_overview/<int:operation_id>/vehicle-assignments/<int:helper_id>", methods=["PUT"])
def api_vehicle_assignment(operation_id, helper_id):
    if get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"vehicle_id", "role"} or "vehicle_id" not in payload:
        return _vehicle_error("Die Fahrzeugzuordnung ist ungültig.")
    try:
        assign_helper(
            operation_id, helper_id, payload.get("vehicle_id"), payload.get("role", "member")
        )
    except VehiclePayloadError as exc:
        status = 404 if "nicht gefunden" in str(exc) else 400
        return _vehicle_error(exc, status)
    _emit_vehicles_changed(operation_id)
    _emit_helper_event("helper_saved", operation_id)
    return jsonify({"ok": True})


@bp.route("/api/vehicle-templates", methods=["GET"])
def api_vehicle_templates_list():
    return jsonify({"items": list_templates()})


@bp.route("/api/vehicle-templates", methods=["POST"])
def api_vehicle_templates_create():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"operation_id", "name", "overwrite"}:
        return _vehicle_error("Die Vorlagenanfrage ist ungültig.")
    operation_id = payload.get("operation_id")
    if type(operation_id) is not int or get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    try:
        template, overwritten = save_template(
            operation_id, payload.get("name"), payload.get("overwrite") is True
        )
    except FileExistsError as exc:
        return _vehicle_error(exc, 409)
    except VehicleTemplateError as exc:
        return _vehicle_error(exc)
    _emit_templates_changed()
    return jsonify({
        "id": template["id"], "name": template["name"],
        "vehicle_count": len(template["vehicles"]), "overwritten": overwritten,
    }), 200 if overwritten else 201


@bp.route("/api/vehicle-templates/<template_id>", methods=["GET"])
def api_vehicle_template_get(template_id):
    try:
        template = get_template(template_id)
    except VehicleTemplateError as exc:
        return _vehicle_error(exc)
    if template is None:
        return _vehicle_error("Vorlage nicht gefunden.", 404)
    return jsonify(template)


@bp.route("/api/vehicle-templates/<template_id>", methods=["DELETE"])
def api_vehicle_template_delete(template_id):
    try:
        deleted = delete_template(template_id)
    except VehicleTemplateError as exc:
        return _vehicle_error(exc)
    if not deleted:
        return _vehicle_error("Vorlage nicht gefunden.", 404)
    _emit_templates_changed()
    return '', 204


@bp.route("/api/vehicle-templates/<template_id>/apply", methods=["POST"])
def api_vehicle_template_apply(template_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"operation_id", "mode"}:
        return _vehicle_error("Die Vorlagenanfrage ist ungültig.")
    operation_id = payload.get("operation_id")
    if type(operation_id) is not int or get_operation(operation_id) is None:
        return _vehicle_error("Lage nicht gefunden.", 404)
    try:
        result = apply_template(template_id, operation_id, payload.get("mode"))
    except (VehicleTemplateError, VehiclePayloadError) as exc:
        status = 404 if "nicht gefunden" in str(exc) else 400
        return _vehicle_error(exc, status)
    _emit_vehicles_changed(operation_id)
    _emit_helper_event("helper_saved", operation_id)
    return jsonify(result)

@bp.route("/api/operation_overview/<int:operation_id>")
def api_operation_overview_get(operation_id):
    operation = get_operation(operation_id)
    missions = get_missions(operation_id)
    for mission in missions:
        mission["persons"] = get_persons(mission["id"])
    operation["missions"] = missions
    return jsonify(operation)

@bp.route("/api/operation_overview/<int:operation_id>/export")
def export_operation_pdf(operation_id):
    operation = get_operation(operation_id)
    if operation is None:
        return jsonify({"error": "Lage nicht gefunden."}), 404

    requested_sections = request.args.getlist("section")
    if not request.args:
        sections = [SECTION_PATIENTS]
    elif not requested_sections:
        return jsonify({"error": "Bitte mindestens einen Exportbereich auswählen."}), 400
    else:
        sections = []
        for section in requested_sections:
            if section not in SECTION_ORDER:
                return jsonify({"error": "Ein Exportbereich ist ungültig."}), 400
            if section not in sections:
                sections.append(section)

    bundle = request.args.get("bundle", "pdf")
    if bundle not in {"pdf", "zip"}:
        return jsonify({"error": "Das Exportformat ist ungültig."}), 400

    missions = get_missions(operation_id)
    for mission in missions:
        mission["persons"] = get_persons(mission["id"])
    operation["missions"] = missions

    helpers = (
        list_helpers(operation_id)
        if {SECTION_HELPERS_SUMMARY, SECTION_HELPERS_DETAIL}.intersection(sections)
        else None
    )
    vehicles = list_vehicles(operation_id) if SECTION_VEHICLES in sections else None

    safe_name = re.sub(
        r"[^A-Za-z0-9ÄÖÜäöüß_-]+", "_", operation.get("name") or str(operation_id)
    ).strip("_") or str(operation_id)
    date_suffix = datetime.date.today().isoformat()

    if bundle == "zip":
        section_filenames = {
            SECTION_PATIENTS: "Patienten.pdf",
            SECTION_HELPERS_SUMMARY: "Helfer_Uebersicht.pdf",
            SECTION_HELPERS_DETAIL: "Helfer_Detail.pdf",
            SECTION_VEHICLES: "Fahrzeuge.pdf",
        }
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for section in sections:
                archive.writestr(
                    section_filenames[section],
                    generate_operation_pdf(
                        operation, [section], helpers=helpers, vehicles=vehicles
                    ),
                )
        artifact_bytes = output.getvalue()
        filename = f"Lage_{safe_name}_Export_{date_suffix}.zip"
        mimetype = "application/zip"
    else:
        artifact_bytes = generate_operation_pdf(
            operation, sections, helpers=helpers, vehicles=vehicles
        )
        section_names = {
            SECTION_PATIENTS: "Patienten",
            SECTION_HELPERS_SUMMARY: "Helfer_Uebersicht",
            SECTION_HELPERS_DETAIL: "Helfer_Detail",
            SECTION_VEHICLES: "Fahrzeuge",
        }
        label = section_names[sections[0]] if len(sections) == 1 else "Gesamt"
        filename = f"Lage_{safe_name}_{label}_{date_suffix}.pdf"
        mimetype = "application/pdf"

    export_path = os.getenv("PDF_EXPORT_PATH", "").strip()
    if export_path:
        os.makedirs(export_path, exist_ok=True)
        with open(os.path.join(export_path, filename), "wb") as export_file:
            export_file.write(artifact_bytes)

    return send_file(
        BytesIO(artifact_bytes),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


def register(app, socketio):
    global _socketio
    _socketio = socketio
    app.register_blueprint(bp)
    register_socket_events(socketio)
