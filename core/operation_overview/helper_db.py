import re
import sqlite3
import time
import unicodedata
from datetime import datetime

from core.db import get_db
from core.operation_overview.helper_parser import (
    HelperPayloadError,
    NUTRITION_VALUES,
    normalize_gender,
    parse_birth_date,
    parse_deployment_datetime,
)


EDITABLE_FIELDS = (
    "last_name", "first_name", "birth_date", "gender", "postal_code", "city",
    "nationality", "street", "mobile", "email", "nutrition_type", "nutrition_note",
    "district_association", "community", "deployment_location", "deployment_info",
    "deployment_start", "deployment_end", "membership_number",
    "district_association_raw", "card_number", "verification_code",
)
SOURCE_ORDER = ("Meldekarte-QR", "DRK-Server-QR", "Manuell")
VALID_SOURCES = set(SOURCE_ORDER)
VALID_STATUSES = {"Anwesend", "Abgemeldet"}
QUALIFICATIONS = (
    "ZF", "EL", "TF", "WR", "Taucher", "Fließ-WR", "RS-WRD", "SAN",
    "SanFD", "RS", "NotSan", "Arzt",
)
VALID_QUALIFICATIONS = set(QUALIFICATIONS)
QUALIFICATION_LABELS = {
    "ZF": "Zugführer",
    "EL": "Einsatzleiter",
    "TF": "Truppführer",
    "WR": "Wasserretter",
    "Taucher": "Taucher",
    "Fließ-WR": "Fließwasserretter",
    "RS-WRD": "Rettungsschwimmer im Wasserrettungsdienst",
    "SAN": "Sanitäter",
    "SanFD": "Sanitär mit Fachdienstausbildung",
    "RS": "Rettungssanitäter",
    "NotSan": "Notfallsanitäter",
    "Arzt": "Arzt",
}


def _current_local_datetime():
    return (
        datetime.now().astimezone().replace(tzinfo=None, second=0, microsecond=0)
        .isoformat(timespec="minutes")
    )


def _clean(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def _identity_part(value):
    value = unicodedata.normalize("NFKC", _clean(value) or "")
    return value.casefold()


def identity_key(last_name, first_name, birth_date):
    return "|".join((_identity_part(last_name), _identity_part(first_name), birth_date or ""))


def normalize_helper_data(data, partial=False):
    if not isinstance(data, dict):
        raise HelperPayloadError("Die Helferdaten sind ungültig.")

    result = {}
    for field in EDITABLE_FIELDS:
        if partial and field not in data:
            continue
        value = data.get(field)
        if field == "birth_date":
            result[field] = parse_birth_date(value) if value else None
        elif field == "gender":
            result[field] = normalize_gender(value)
        elif field in ("deployment_start", "deployment_end"):
            result[field] = parse_deployment_datetime(value)
        elif field == "nutrition_type":
            value = _clean(value)
            if value and value not in NUTRITION_VALUES:
                raise HelperPayloadError("Die Ernährungsart ist ungültig.")
            result[field] = value
        else:
            result[field] = _clean(value)

    if not partial or "qualifications" in data:
        qualifications = data.get("qualifications") or []
        if not isinstance(qualifications, list):
            raise HelperPayloadError("Die Qualifikationen sind ungültig.")
        normalized_qualifications = []
        for qualification in qualifications:
            qualification = _clean(qualification)
            if qualification not in VALID_QUALIFICATIONS:
                raise HelperPayloadError("Eine Qualifikation ist ungültig.")
            if qualification not in normalized_qualifications:
                normalized_qualifications.append(qualification)
        result["qualifications"] = normalized_qualifications

    if not partial:
        missing = [
            label for field, label in (
                ("last_name", "Nachname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
            ) if not result.get(field)
        ]
        if missing:
            raise HelperPayloadError("Pflichtfelder fehlen: " + ", ".join(missing) + ".")
    return result


def _get_sources(con, helper_id):
    rows = con.execute(
        "SELECT source FROM overview_helper_sources WHERE helper_id = ?", (helper_id,)
    ).fetchall()
    found = {row["source"] for row in rows}
    return [source for source in SOURCE_ORDER if source in found]


def _get_qualifications(con, helper_id):
    rows = con.execute(
        "SELECT qualification FROM overview_helper_qualifications WHERE helper_id = ?",
        (helper_id,),
    ).fetchall()
    found = {row["qualification"] for row in rows}
    return [qualification for qualification in QUALIFICATIONS if qualification in found]


def _set_qualifications(con, helper_id, qualifications):
    con.execute(
        "DELETE FROM overview_helper_qualifications WHERE helper_id = ?", (helper_id,)
    )
    con.executemany(
        "INSERT INTO overview_helper_qualifications (helper_id, qualification) VALUES (?, ?)",
        ((helper_id, qualification) for qualification in qualifications),
    )


def _serialize(con, row):
    if row is None:
        return None
    helper = dict(row)
    sources = _get_sources(con, helper["id"])
    helper["sources"] = sources
    helper["source_display"] = " + ".join(sources)
    helper["source_category"] = "Kombiniert" if len(sources) > 1 else (sources[0] if sources else "")
    helper["qualifications"] = _get_qualifications(con, helper["id"])
    assignment = con.execute(
        """
        SELECT a.vehicle_id, a.role, v.call_sign AS vehicle_call_sign
        FROM overview_vehicle_assignments a
        JOIN overview_vehicles v ON v.id = a.vehicle_id
        WHERE a.helper_id = ?
        """,
        (helper["id"],),
    ).fetchone()
    helper["vehicle_id"] = assignment["vehicle_id"] if assignment else None
    helper["vehicle_role"] = assignment["role"] if assignment else None
    helper["vehicle_call_sign"] = assignment["vehicle_call_sign"] if assignment else None
    return helper


def get_helper(helper_id, operation_id=None, con=None):
    own_connection = con is None
    con = con or get_db()
    query = "SELECT * FROM overview_helpers WHERE id = ?"
    params = [helper_id]
    if operation_id is not None:
        query += " AND operation_id = ?"
        params.append(operation_id)
    row = con.execute(query, params).fetchone()
    result = _serialize(con, row)
    if own_connection:
        con.close()
    return result


def find_duplicate(operation_id, data, con=None):
    normalized = normalize_helper_data(data)
    key = identity_key(normalized["last_name"], normalized["first_name"], normalized["birth_date"])
    own_connection = con is None
    con = con or get_db()
    row = con.execute(
        "SELECT * FROM overview_helpers WHERE operation_id = ? AND identity_key = ?",
        (operation_id, key),
    ).fetchone()
    result = _serialize(con, row)
    if own_connection:
        con.close()
    return result


def _comparison_value(field, value):
    if value is None:
        return None
    if field == "mobile":
        digits = re.sub(r"\D", "", value)
        return "49" + digits[2:] if digits.startswith("00") else digits
    if field == "email":
        return value.casefold()
    return _identity_part(value)


def get_conflicts(existing, incoming):
    if not existing:
        return []
    conflicts = []
    for field in EDITABLE_FIELDS:
        current = existing.get(field)
        new = incoming.get(field)
        if current and new and _comparison_value(field, current) != _comparison_value(field, new):
            conflicts.append({"field": field, "existing": current, "incoming": new})
    return conflicts


def create_or_merge(operation_id, data, source):
    if source not in VALID_SOURCES:
        raise HelperPayloadError("Die Erfassungsquelle ist ungültig.")
    normalized = normalize_helper_data(data)
    qualifications = normalized.pop("qualifications")
    # Keep the current time as the default while preserving an explicitly
    # edited value from the registration form or API client.
    normalized["deployment_start"] = (
        normalized.get("deployment_start") or _current_local_datetime()
    )
    key = identity_key(normalized["last_name"], normalized["first_name"], normalized["birth_date"])
    con = get_db()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM overview_helpers WHERE operation_id = ? AND identity_key = ?",
            (operation_id, key),
        ).fetchone()
        merged = row is not None
        conflicts = []
        complemented = []
        if row is None:
            columns = ["operation_id", *EDITABLE_FIELDS, "status", "registered_at", "identity_key"]
            values = [operation_id, *[normalized.get(field) for field in EDITABLE_FIELDS],
                      "Anwesend", int(time.time()), key]
            placeholders = ", ".join("?" for _ in columns)
            cur = con.execute(
                f"INSERT INTO overview_helpers ({', '.join(columns)}) VALUES ({placeholders})", values
            )
            helper_id = cur.lastrowid
        else:
            existing = dict(row)
            helper_id = existing["id"]
            conflicts = get_conflicts(existing, normalized)
            additions = {
                field: normalized[field]
                for field in EDITABLE_FIELDS
                if not existing.get(field) and normalized.get(field)
            }
            if additions:
                assignment = ", ".join(f"{field} = ?" for field in additions)
                con.execute(
                    f"UPDATE overview_helpers SET {assignment} WHERE id = ?",
                    [*additions.values(), helper_id],
                )
                complemented = list(additions)

        if row is None:
            _set_qualifications(con, helper_id, qualifications)
        elif qualifications:
            existing_qualifications = _get_qualifications(con, helper_id)
            _set_qualifications(
                con,
                helper_id,
                [*existing_qualifications, *(
                    qualification for qualification in qualifications
                    if qualification not in existing_qualifications
                )],
            )

        con.execute(
            "INSERT OR IGNORE INTO overview_helper_sources (helper_id, source) VALUES (?, ?)",
            (helper_id, source),
        )
        con.commit()
        helper = get_helper(helper_id, operation_id, con=con)
        return helper, merged, complemented, conflicts
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise HelperPayloadError("Diese Person ist in der Lage bereits vorhanden.") from exc
    finally:
        con.close()


def update_helper(operation_id, helper_id, changes):
    normalized = normalize_helper_data(changes, partial=True)
    qualifications_provided = "qualifications" in normalized
    qualifications = normalized.pop("qualifications", None)
    status_provided = "status" in changes
    status = changes.get("status")
    if status_provided and status not in VALID_STATUSES:
        raise HelperPayloadError("Der Status ist ungültig.")
    if not normalized and not status_provided and not qualifications_provided:
        return get_helper(helper_id, operation_id)

    con = get_db()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM overview_helpers WHERE id = ? AND operation_id = ?",
            (helper_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        current = dict(row)
        result_data = {field: normalized.get(field, current.get(field)) for field in EDITABLE_FIELDS}
        if not result_data["last_name"] or not result_data["first_name"] or not result_data["birth_date"]:
            raise HelperPayloadError("Nachname, Vorname und Geburtsdatum sind Pflichtfelder.")
        new_key = identity_key(result_data["last_name"], result_data["first_name"], result_data["birth_date"])
        updates = dict(normalized)
        updates["identity_key"] = new_key
        if status_provided:
            updates["status"] = status
            if status == "Abgemeldet" and not result_data.get("deployment_end"):
                updates["deployment_end"] = _current_local_datetime()
            if status == "Abgemeldet":
                con.execute(
                    "DELETE FROM overview_vehicle_assignments WHERE helper_id = ?",
                    (helper_id,),
                )
        if updates:
            assignment = ", ".join(f"{field} = ?" for field in updates)
            con.execute(
                f"UPDATE overview_helpers SET {assignment} WHERE id = ? AND operation_id = ?",
                [*updates.values(), helper_id, operation_id],
            )
        if qualifications_provided:
            _set_qualifications(con, helper_id, qualifications)
        con.commit()
        return get_helper(helper_id, operation_id, con=con)
    except sqlite3.IntegrityError as exc:
        con.rollback()
        raise HelperPayloadError("Eine Person mit diesen Identitätsdaten ist bereits vorhanden.") from exc
    finally:
        con.close()


def delete_helper(operation_id, helper_id):
    con = get_db()
    cur = con.execute(
        "DELETE FROM overview_helpers WHERE id = ? AND operation_id = ?", (helper_id, operation_id)
    )
    con.commit()
    deleted = cur.rowcount > 0
    con.close()
    return deleted


def list_helpers(operation_id, q="", vehicle="", qualification="", nutrition="", status=""):
    con = get_db()
    conditions = ["operation_id = ?"]
    params = [operation_id]
    if q:
        term = f"%{q.strip()}%"
        qualification_label_case = "CASE q.qualification " + " ".join(
            "WHEN ? THEN ?" for _ in QUALIFICATION_LABELS
        ) + " ELSE q.qualification END"
        conditions.append(
            "(" + " OR ".join(
                f"{field} LIKE ? COLLATE NOCASE" for field in (
                    "last_name", "first_name", "district_association", "community",
                    "mobile", "deployment_location",
                )
            )
            + " OR CASE gender WHEN 'm' THEN 'Männlich' WHEN 'w' THEN 'Weiblich' "
              "WHEN 'd' THEN 'Divers' ELSE 'Keine Angabe' END LIKE ? COLLATE NOCASE"
            + " OR EXISTS (SELECT 1 FROM overview_helper_qualifications q "
              "WHERE q.helper_id = overview_helpers.id AND "
              f"(q.qualification LIKE ? COLLATE NOCASE OR {qualification_label_case} LIKE ? COLLATE NOCASE))"
            + " OR EXISTS (SELECT 1 FROM overview_vehicle_assignments a "
              "JOIN overview_vehicles v ON v.id = a.vehicle_id "
              "WHERE a.helper_id = overview_helpers.id AND "
              "(v.call_sign LIKE ? COLLATE NOCASE OR v.vehicle_type LIKE ? COLLATE NOCASE))"
            + ")"
        )
        params.extend([term] * 7)
        params.append(term)
        for short, label in QUALIFICATION_LABELS.items():
            params.extend([short, label])
        params.extend([term, term, term])
    if vehicle == "unassigned":
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM overview_vehicle_assignments a WHERE a.helper_id = overview_helpers.id)"
        )
    elif vehicle:
        try:
            vehicle_id = int(vehicle)
        except (TypeError, ValueError):
            vehicle_id = -1
        conditions.append(
            "EXISTS (SELECT 1 FROM overview_vehicle_assignments a "
            "WHERE a.helper_id = overview_helpers.id AND a.vehicle_id = ?)"
        )
        params.append(vehicle_id)
    if qualification:
        conditions.append(
            "EXISTS (SELECT 1 FROM overview_helper_qualifications q "
            "WHERE q.helper_id = overview_helpers.id AND q.qualification = ?)"
        )
        params.append(qualification)
    if nutrition:
        conditions.append("nutrition_type = ?")
        params.append(nutrition)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = " AND ".join(conditions)
    total = con.execute(f"SELECT COUNT(*) FROM overview_helpers WHERE {where}", params).fetchone()[0]
    rows = con.execute(
        f"SELECT * FROM overview_helpers WHERE {where} "
        "ORDER BY registered_at DESC, id DESC",
        params,
    ).fetchall()
    items = [_serialize(con, row) for row in rows]

    stat_rows = con.execute(
        "SELECT status, gender, nutrition_type FROM overview_helpers WHERE operation_id = ?", (operation_id,)
    ).fetchall()
    stats = {
        "total": len(stat_rows),
        "status": {"Anwesend": 0, "Abgemeldet": 0},
        "gender": {"m": 0, "w": 0, "d": 0, "none": 0},
        "nutrition": {value: 0 for value in NUTRITION_VALUES},
    }
    for row in stat_rows:
        stats["status"][row["status"]] += 1
        if row["status"] == "Anwesend":
            stats["gender"][row["gender"] or "none"] += 1
            if row["nutrition_type"]:
                stats["nutrition"].setdefault(row["nutrition_type"], 0)
                stats["nutrition"][row["nutrition_type"]] += 1

    con.close()
    return {
        "items": items,
        "total": total,
        "stats": stats,
    }
