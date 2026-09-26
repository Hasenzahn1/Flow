import re
from datetime import datetime
from urllib.parse import unquote


class HelperPayloadError(ValueError):
    pass


NUTRITION_VALUES = (
    "ohne Einschränkung",
    "vegetarisch",
    "vegan",
    "Fruktoseintoleranz",
    "Laktoseintoleranz",
    "Sonstiges",
)


def _clean(value):
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def _decode_field(value):
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise HelperPayloadError("Der DRK-QR-Code enthält eine ungültige URL-Kodierung.")
    try:
        return _clean(unquote(value, encoding="utf-8", errors="strict"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HelperPayloadError("Der DRK-QR-Code enthält eine ungültige URL-Kodierung.") from exc


def parse_birth_date(value):
    value = _clean(value)
    if not value:
        raise HelperPayloadError("Das Geburtsdatum fehlt.")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise HelperPayloadError("Das Geburtsdatum muss im Format TT.MM.JJJJ vorliegen.")


def parse_deployment_datetime(value):
    value = _clean(value)
    if not value:
        return None
    for fmt in ("%d.%m.%Y - %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            pass
    raise HelperPayloadError("Einsatzzeiten müssen im Format TT.MM.JJJJ - HH:MM vorliegen.")


def normalize_gender(value):
    value = (_clean(value) or "").casefold()
    aliases = {
        "m": "m", "männlich": "m", "maennlich": "m",
        "w": "w", "weiblich": "w",
        "d": "d", "divers": "d",
    }
    if not value:
        return None
    if value not in aliases:
        raise HelperPayloadError("Geschlecht muss m, w oder d sein.")
    return aliases[value]


def normalize_nutrition(value):
    value = _clean(value)
    if not value:
        return None, None
    value = re.sub(r"^Ernährung\s*", "", value, flags=re.IGNORECASE).strip()
    by_folded = {item.casefold(): item for item in NUTRITION_VALUES}
    canonical = by_folded.get(value.casefold())
    if canonical:
        return canonical, None
    if value.casefold().startswith("sonstiges"):
        note = re.sub(r"^sonstiges\s*[:\-]?\s*", "", value, flags=re.IGNORECASE)
        return "Sonstiges", note or None
    return "Sonstiges", value


def extract_district_association(raw_value):
    raw_value = _clean(raw_value)
    if not raw_value:
        return None
    match = re.match(r"^\d+\s+Kreisverband\s+(.+)$", raw_value, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else None


def _require_identity(data):
    missing = []
    if not data.get("last_name"):
        missing.append("Nachname")
    if not data.get("first_name"):
        missing.append("Vorname")
    if not data.get("birth_date"):
        missing.append("Geburtsdatum")
    if missing:
        raise HelperPayloadError("Pflichtfelder fehlen: " + ", ".join(missing) + ".")


def parse_helper_payload(raw_payload):
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        raise HelperPayloadError("Es wurden keine Scannerdaten empfangen.")

    raw_fields = raw_payload.strip().split(";")
    if len(raw_fields) == 16:
        fields = [_clean(value) for value in raw_fields]
        nutrition_type, nutrition_note = normalize_nutrition(fields[15])
        data = {
            "last_name": fields[0],
            "first_name": fields[1],
            "birth_date": parse_birth_date(fields[2]),
            "gender": normalize_gender(fields[3]),
            "postal_code": fields[4],
            "city": fields[5],
            "nationality": fields[6],
            "street": fields[7],
            "mobile": fields[8],
            "email": None,
            "district_association": fields[9],
            "community": fields[10],
            "deployment_location": fields[11],
            "deployment_info": fields[12],
            "deployment_start": parse_deployment_datetime(fields[13]),
            "deployment_end": parse_deployment_datetime(fields[14]),
            "nutrition_type": nutrition_type,
            "nutrition_note": nutrition_note,
            "membership_number": None,
            "district_association_raw": None,
            "card_number": None,
            "verification_code": None,
        }
        source = "Meldekarte-QR"
    elif len(raw_fields) == 19:
        fields = [_decode_field(value) for value in raw_fields]
        district_raw = fields[9]
        data = {
            "last_name": fields[0],
            "first_name": fields[1],
            "birth_date": parse_birth_date(fields[2]),
            "gender": normalize_gender(fields[3]),
            "postal_code": fields[4],
            "city": fields[5],
            "nationality": fields[6],
            "street": fields[7],
            "mobile": fields[15],
            "email": fields[16],
            "district_association": extract_district_association(district_raw),
            "community": fields[10],
            "deployment_location": None,
            "deployment_info": None,
            "deployment_start": None,
            "deployment_end": None,
            "nutrition_type": None,
            "nutrition_note": None,
            "membership_number": fields[8],
            "district_association_raw": district_raw,
            "card_number": fields[17],
            "verification_code": fields[18],
        }
        source = "DRK-Server-QR"
    else:
        raise HelperPayloadError(
            f"Unbekannter QR-Code: Erwartet wurden 16 oder 19 Felder, erkannt wurden {len(raw_fields)}."
        )

    _require_identity(data)
    return {"source": source, "data": data}
