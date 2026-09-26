import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone

from core.operation_overview.vehicle_db import (
    VehiclePayloadError,
    apply_vehicle_template,
    normalize_vehicle_data,
    vehicle_template_values,
)


TEMPLATE_DIR = os.getenv("FLOW_VEHICLE_TEMPLATE_PATH", "data/vehicle_templates")
SCHEMA_VERSION = 1
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class VehicleTemplateError(ValueError):
    pass


def _clean_name(value):
    if not isinstance(value, str):
        raise VehicleTemplateError("Bitte einen Vorlagennamen angeben.")
    value = re.sub(r"\s+", " ", value).strip()
    if not value or len(value) > 80 or any(ord(char) < 32 for char in value):
        raise VehicleTemplateError("Der Vorlagenname muss zwischen 1 und 80 Zeichen lang sein.")
    return value


def _path(template_id):
    if not isinstance(template_id, str) or not ID_PATTERN.fullmatch(template_id):
        raise VehicleTemplateError("Die Vorlagen-ID ist ungültig.")
    return os.path.join(TEMPLATE_DIR, f"{template_id}.json")


def _validate_document(document, template_id=None):
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise VehicleTemplateError("Unbekanntes oder ungültiges Vorlagenformat.")
    doc_id = document.get("id")
    if not isinstance(doc_id, str) or not ID_PATTERN.fullmatch(doc_id):
        raise VehicleTemplateError("Die Vorlagen-ID ist ungültig.")
    if template_id is not None and doc_id != template_id:
        raise VehicleTemplateError("Dateiname und Vorlagen-ID stimmen nicht überein.")
    name = _clean_name(document.get("name"))
    vehicles = document.get("vehicles")
    if not isinstance(vehicles, list):
        raise VehicleTemplateError("Die Fahrzeugliste der Vorlage ist ungültig.")
    try:
        normalized = [normalize_vehicle_data(vehicle) for vehicle in vehicles]
    except VehiclePayloadError as exc:
        raise VehicleTemplateError(str(exc)) from exc
    return {
        "id": doc_id,
        "name": name,
        "schema_version": SCHEMA_VERSION,
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
        "vehicles": normalized,
    }


def get_template(template_id):
    path = _path(template_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            return _validate_document(json.load(file), template_id)
    except (OSError, json.JSONDecodeError) as exc:
        raise VehicleTemplateError("Die Vorlagendatei kann nicht gelesen werden.") from exc


def list_templates():
    if not os.path.isdir(TEMPLATE_DIR):
        return []
    result = []
    for filename in sorted(os.listdir(TEMPLATE_DIR)):
        if not filename.endswith(".json"):
            continue
        template_id = filename[:-5]
        if not ID_PATTERN.fullmatch(template_id):
            result.append({"id": template_id, "name": filename, "invalid": True,
                           "error": "Ungültiger Dateiname"})
            continue
        try:
            document = get_template(template_id)
            result.append({
                "id": document["id"], "name": document["name"],
                "created_at": document["created_at"], "updated_at": document["updated_at"],
                "vehicle_count": len(document["vehicles"]), "invalid": False,
            })
        except VehicleTemplateError as exc:
            result.append({"id": template_id, "name": filename, "invalid": True, "error": str(exc)})
    return sorted(result, key=lambda item: (item.get("invalid", False), item["name"].casefold()))


def save_template(operation_id, name, overwrite=False):
    name = _clean_name(name)
    existing = next(
        (item for item in list_templates()
         if not item.get("invalid") and item["name"].casefold() == name.casefold()),
        None,
    )
    if existing and not overwrite:
        raise FileExistsError("Eine Vorlage mit diesem Namen existiert bereits.")
    template_id = existing["id"] if existing else uuid.uuid4().hex
    previous = get_template(template_id) if existing else None
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "schema_version": SCHEMA_VERSION,
        "id": template_id,
        "name": name,
        "created_at": previous.get("created_at") if previous else now,
        "updated_at": now,
        "vehicles": vehicle_template_values(operation_id),
    }
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    target = _path(template_id)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=TEMPLATE_DIR, prefix=f".{template_id}-",
            suffix=".tmp", delete=False
        ) as file:
            json.dump(document, file, ensure_ascii=False, indent=2)
            file.write("\n")
            temporary = file.name
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return _validate_document(document, template_id), existing is not None


def delete_template(template_id):
    path = _path(template_id)
    if not os.path.isfile(path):
        return False
    os.unlink(path)
    return True


def apply_template(template_id, operation_id, mode):
    document = get_template(template_id)
    if document is None:
        raise VehicleTemplateError("Vorlage nicht gefunden.")
    return apply_vehicle_template(operation_id, document["vehicles"], mode)
