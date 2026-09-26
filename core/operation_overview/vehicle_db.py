import re
from collections import Counter

from core.db import get_db


VEHICLE_FIELDS = ("call_sign", "vehicle_type", "phone", "target_occupancy", "max_seats")
VALID_ROLES = {"member", "leader"}


class VehiclePayloadError(ValueError):
    pass


def _clean(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def normalize_vehicle_data(data, partial=False):
    if not isinstance(data, dict):
        raise VehiclePayloadError("Die Fahrzeugdaten sind ungültig.")
    unknown = set(data) - set(VEHICLE_FIELDS)
    if unknown:
        raise VehiclePayloadError("Die Anfrage enthält unbekannte Fahrzeugfelder.")

    result = {}
    for field in VEHICLE_FIELDS:
        if partial and field not in data:
            continue
        value = data.get(field)
        if field in {"target_occupancy", "max_seats"}:
            if isinstance(value, bool):
                raise VehiclePayloadError("Soll- und Maximalbesetzung müssen ganze Zahlen sein.")
            try:
                number = int(value)
            except (TypeError, ValueError) as exc:
                raise VehiclePayloadError("Soll- und Maximalbesetzung müssen ganze Zahlen sein.") from exc
            if number < 1:
                raise VehiclePayloadError("Soll- und Maximalbesetzung müssen mindestens 1 sein.")
            result[field] = number
        else:
            result[field] = _clean(value)

    if not partial:
        if not result.get("call_sign") or not result.get("vehicle_type"):
            raise VehiclePayloadError("Funkrufname und Fahrzeugtyp sind Pflichtfelder.")
        if result["target_occupancy"] > result["max_seats"]:
            raise VehiclePayloadError("Die Sollbesetzung darf die Maximalsitze nicht überschreiten.")
    return result


def _crew(con, vehicle_id):
    rows = con.execute(
        """
        SELECT h.id, h.first_name, h.last_name, h.mobile, a.role
        FROM overview_vehicle_assignments a
        JOIN overview_helpers h ON h.id = a.helper_id
        WHERE a.vehicle_id = ?
        ORDER BY CASE a.role WHEN 'leader' THEN 0 ELSE 1 END,
                 h.last_name COLLATE NOCASE, h.first_name COLLATE NOCASE
        """,
        (vehicle_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def vehicle_status(vehicle, crew_count=None):
    count = len(vehicle.get("crew", [])) if crew_count is None else crew_count
    has_leader = bool(vehicle.get("leader") or any(p.get("role") == "leader" for p in vehicle.get("crew", [])))
    if count > vehicle["max_seats"]:
        return "Überbelegt"
    if count == 0:
        return "Unbesetzt"
    if not has_leader or count < vehicle["target_occupancy"]:
        return "Unvollständig"
    if count == vehicle["max_seats"]:
        return "Voll"
    return "Gut besetzt"


def _serialize_vehicle(con, row):
    if row is None:
        return None
    vehicle = dict(row)
    vehicle["crew"] = _crew(con, vehicle["id"])
    vehicle["leader"] = next((person for person in vehicle["crew"] if person["role"] == "leader"), None)
    vehicle["leader_id"] = vehicle["leader"]["id"] if vehicle["leader"] else None
    vehicle["crew_count"] = len(vehicle["crew"])
    vehicle["free_seats"] = vehicle["max_seats"] - vehicle["crew_count"]
    vehicle["over_capacity_by"] = max(0, -vehicle["free_seats"])
    vehicle["status"] = vehicle_status(vehicle)
    return vehicle


def get_vehicle(operation_id, vehicle_id, con=None):
    own_connection = con is None
    con = con or get_db()
    row = con.execute(
        "SELECT * FROM overview_vehicles WHERE id = ? AND operation_id = ?",
        (vehicle_id, operation_id),
    ).fetchone()
    result = _serialize_vehicle(con, row)
    if own_connection:
        con.close()
    return result


def _available_helpers(con, operation_id):
    rows = con.execute(
        """
        SELECT h.id, h.first_name, h.last_name, h.mobile, h.status,
               a.vehicle_id, a.role, v.call_sign AS vehicle_call_sign
        FROM overview_helpers h
        LEFT JOIN overview_vehicle_assignments a ON a.helper_id = h.id
        LEFT JOIN overview_vehicles v ON v.id = a.vehicle_id
        WHERE h.operation_id = ?
        ORDER BY h.last_name COLLATE NOCASE, h.first_name COLLATE NOCASE
        """,
        (operation_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_vehicles(operation_id):
    con = get_db()
    rows = con.execute(
        "SELECT * FROM overview_vehicles WHERE operation_id = ? ORDER BY order_index, id",
        (operation_id,),
    ).fetchall()
    items = [_serialize_vehicle(con, row) for row in rows]
    statuses = Counter(vehicle["status"] for vehicle in items)
    result = {
        "items": items,
        "total": len(items),
        "stats": {
            "occupied": sum(vehicle["crew_count"] for vehicle in items),
            "max_seats": sum(vehicle["max_seats"] for vehicle in items),
            "statuses": dict(statuses),
        },
        "vehicle_types": sorted({vehicle["vehicle_type"] for vehicle in items}, key=str.casefold),
        "helpers": _available_helpers(con, operation_id),
    }
    con.close()
    return result


def count_vehicles(operation_id):
    con = get_db()
    count = con.execute(
        "SELECT COUNT(*) FROM overview_vehicles WHERE operation_id = ?", (operation_id,)
    ).fetchone()[0]
    con.close()
    return count


def create_vehicle(operation_id, data, con=None):
    values = normalize_vehicle_data(data)
    own_connection = con is None
    con = con or get_db()
    order_index = con.execute(
        "SELECT COALESCE(MAX(order_index), -1) + 1 FROM overview_vehicles WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()[0]
    cur = con.execute(
        """
        INSERT INTO overview_vehicles
            (operation_id, call_sign, vehicle_type, phone, target_occupancy, max_seats, order_index)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (operation_id, values["call_sign"], values["vehicle_type"], values["phone"],
         values["target_occupancy"], values["max_seats"], order_index),
    )
    if own_connection:
        con.commit()
    result = get_vehicle(operation_id, cur.lastrowid, con=con)
    if own_connection:
        con.close()
    return result


def update_vehicle(operation_id, vehicle_id, changes):
    normalized = normalize_vehicle_data(changes, partial=True)
    if not normalized:
        return get_vehicle(operation_id, vehicle_id)
    con = get_db()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM overview_vehicles WHERE id = ? AND operation_id = ?",
            (vehicle_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        merged = dict(row)
        merged.update(normalized)
        if not merged.get("call_sign") or not merged.get("vehicle_type"):
            raise VehiclePayloadError("Funkrufname und Fahrzeugtyp sind Pflichtfelder.")
        if merged["target_occupancy"] > merged["max_seats"]:
            raise VehiclePayloadError("Die Sollbesetzung darf die Maximalsitze nicht überschreiten.")
        assignment = ", ".join(f"{field} = ?" for field in normalized)
        con.execute(
            f"UPDATE overview_vehicles SET {assignment} WHERE id = ? AND operation_id = ?",
            [*normalized.values(), vehicle_id, operation_id],
        )
        con.commit()
        return get_vehicle(operation_id, vehicle_id, con=con)
    finally:
        con.close()


def delete_vehicle(operation_id, vehicle_id):
    con = get_db()
    cur = con.execute(
        "DELETE FROM overview_vehicles WHERE id = ? AND operation_id = ?",
        (vehicle_id, operation_id),
    )
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted


def reorder_vehicles(operation_id, vehicle_ids):
    if not isinstance(vehicle_ids, list) or any(type(value) is not int for value in vehicle_ids):
        return False
    if len(vehicle_ids) != len(set(vehicle_ids)):
        return False
    con = get_db()
    current = [row["id"] for row in con.execute(
        "SELECT id FROM overview_vehicles WHERE operation_id = ?", (operation_id,)
    ).fetchall()]
    if set(current) != set(vehicle_ids) or len(current) != len(vehicle_ids):
        con.close()
        return False
    with con:
        con.executemany(
            "UPDATE overview_vehicles SET order_index = ? WHERE id = ? AND operation_id = ?",
            [(index, vehicle_id, operation_id) for index, vehicle_id in enumerate(vehicle_ids)],
        )
    con.close()
    return True


def assign_helper(operation_id, helper_id, vehicle_id, role="member"):
    if role not in VALID_ROLES:
        raise VehiclePayloadError("Die Fahrzeugrolle ist ungültig.")
    con = get_db()
    try:
        con.execute("BEGIN IMMEDIATE")
        helper = con.execute(
            "SELECT id, status FROM overview_helpers WHERE id = ? AND operation_id = ?",
            (helper_id, operation_id),
        ).fetchone()
        if helper is None:
            raise VehiclePayloadError("Helfer nicht gefunden.")
        if vehicle_id is None:
            con.execute("DELETE FROM overview_vehicle_assignments WHERE helper_id = ?", (helper_id,))
            con.commit()
            return None
        if type(vehicle_id) is not int:
            raise VehiclePayloadError("Das Fahrzeug ist ungültig.")
        vehicle = con.execute(
            "SELECT id FROM overview_vehicles WHERE id = ? AND operation_id = ?",
            (vehicle_id, operation_id),
        ).fetchone()
        if vehicle is None:
            raise VehiclePayloadError("Fahrzeug nicht gefunden.")
        if helper["status"] != "Anwesend":
            raise VehiclePayloadError("Nur anwesende Helfer können einem Fahrzeug zugeordnet werden.")
        if role == "leader":
            con.execute(
                "UPDATE overview_vehicle_assignments SET role = 'member' WHERE vehicle_id = ? AND role = 'leader'",
                (vehicle_id,),
            )
        con.execute(
            """
            INSERT INTO overview_vehicle_assignments (helper_id, vehicle_id, role)
            VALUES (?, ?, ?)
            ON CONFLICT(helper_id) DO UPDATE SET vehicle_id = excluded.vehicle_id, role = excluded.role
            """,
            (helper_id, vehicle_id, role),
        )
        con.commit()
        return get_vehicle(operation_id, vehicle_id, con=con)
    finally:
        con.close()


def vehicle_template_values(operation_id):
    con = get_db()
    rows = con.execute(
        """
        SELECT call_sign, vehicle_type, phone, target_occupancy, max_seats
        FROM overview_vehicles WHERE operation_id = ? ORDER BY order_index, id
        """,
        (operation_id,),
    ).fetchall()
    values = [dict(row) for row in rows]
    con.close()
    return values


def apply_vehicle_template(operation_id, vehicles, mode):
    if mode not in {"append", "replace"}:
        raise VehiclePayloadError("Der Lademodus ist ungültig.")
    normalized = [normalize_vehicle_data(vehicle) for vehicle in vehicles]
    con = get_db()
    try:
        con.execute("BEGIN IMMEDIATE")
        if mode == "replace":
            con.execute("DELETE FROM overview_vehicles WHERE operation_id = ?", (operation_id,))
        for values in normalized:
            create_vehicle(operation_id, values, con=con)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return list_vehicles(operation_id)
