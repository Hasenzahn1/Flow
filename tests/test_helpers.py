import os
import tempfile
import unittest
from datetime import datetime

from flask import Flask
from flask_socketio import SocketIO

import core.db as core_db
from core.operation_overview.helper_db import create_or_merge, get_helper, update_helper
from core.operation_overview.helper_parser import HelperPayloadError, parse_helper_payload
from core.operation_overview.operation_db import add_operation
from tools.operation_overview import operation_overview


MELDEKARTE = (
    "Beispiel;Alex;14.05.1995;d;12345;Musterstadt;deutsch;Testweg 7;"
    "+491701234567;Musterkreis;Bereitschaft Nord;Abschnitt A;Logistik;"
    "27.09.2026 - 08:00;;Ernährung ohne Einschränkung"
)

DRK_AUSWEIS = (
    "Beispiel;Alex;14.05.1995;d;12345;Musterstadt;;Testweg%207;100200300;"
    "4090000%20Kreisverband%20Musterkreis;Bereitschaft%20Nord;;Funktion%20Ignoriert;;;"
    "+49%20170%201234567;alex.beispiel%40example.org;654321;abc123def456"
)


class HelperParserTests(unittest.TestCase):
    def test_meldekarte_mapping(self):
        parsed = parse_helper_payload(MELDEKARTE)
        self.assertEqual(parsed["source"], "Meldekarte-QR")
        self.assertEqual(parsed["data"]["birth_date"], "1995-05-14")
        self.assertEqual(parsed["data"]["deployment_start"], "2026-09-27T08:00")
        self.assertEqual(parsed["data"]["nutrition_type"], "ohne Einschränkung")
        self.assertEqual(parsed["data"]["district_association"], "Musterkreis")

    def test_drk_mapping_and_url_decoding(self):
        parsed = parse_helper_payload(DRK_AUSWEIS)
        data = parsed["data"]
        self.assertEqual(parsed["source"], "DRK-Server-QR")
        self.assertEqual(data["street"], "Testweg 7")
        self.assertEqual(data["district_association_raw"], "4090000 Kreisverband Musterkreis")
        self.assertEqual(data["district_association"], "Musterkreis")
        self.assertEqual(data["email"], "alex.beispiel@example.org")
        self.assertEqual(data["card_number"], "654321")

    def test_rejects_unknown_field_count_and_bad_dates(self):
        with self.assertRaises(HelperPayloadError):
            parse_helper_payload("a;b;c")
        values = MELDEKARTE.split(";")
        values[2] = "31.02.2000"
        with self.assertRaises(HelperPayloadError):
            parse_helper_payload(";".join(values))


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core_db.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        core_db.init_db()
        core_db.migrate()
        self.operation = add_operation("Testlage")

    def tearDown(self):
        self.tempdir.cleanup()


class HelperDatabaseTests(DatabaseTestCase):
    def test_qualifications_are_stored_in_canonical_order_and_validated(self):
        helper, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Qualifiziert",
            "first_name": "Alex",
            "birth_date": "1995-05-14",
            "qualifications": ["NotSan", "ZF", "NotSan"],
        }, "Manuell")
        self.assertEqual(helper["qualifications"], ["ZF", "NotSan"])

        updated = update_helper(
            self.operation["id"], helper["id"], {"qualifications": ["EL", "Taucher"]}
        )
        self.assertEqual(updated["qualifications"], ["EL", "Taucher"])

        with self.assertRaises(HelperPayloadError):
            update_helper(
                self.operation["id"], helper["id"], {"qualifications": ["Unbekannt"]}
            )

    def test_registration_preserves_manual_start_and_defaults_when_empty(self):
        parsed = parse_helper_payload(MELDEKARTE)
        manual_start = parsed["data"]["deployment_start"]
        helper, _, _, _ = create_or_merge(
            self.operation["id"], parsed["data"], parsed["source"]
        )
        self.assertEqual(helper["deployment_start"], manual_start)

        before = datetime.now().astimezone().replace(
            tzinfo=None, second=0, microsecond=0
        ).isoformat(timespec="minutes")
        defaulted, _, _, _ = create_or_merge(
            self.operation["id"], {
                "last_name": "Standardzeit",
                "first_name": "Robin",
                "birth_date": "1990-03-20",
            }, "Manuell"
        )
        after = datetime.now().astimezone().replace(
            tzinfo=None, second=0, microsecond=0
        ).isoformat(timespec="minutes")
        self.assertIn(defaulted["deployment_start"], {before, after})

    def test_manual_deployment_end_is_not_overwritten_when_deregistering(self):
        helper, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Einsatzende",
            "first_name": "Alex",
            "birth_date": "1995-05-14",
            "deployment_start": "2026-09-26T18:30",
            "deployment_end": "2026-09-26T20:15",
        }, "Manuell")

        updated = update_helper(
            self.operation["id"], helper["id"], {"status": "Abgemeldet"}
        )
        self.assertEqual(updated["deployment_start"], "2026-09-26T18:30")
        self.assertEqual(updated["deployment_end"], "2026-09-26T20:15")

    def test_merge_fills_blanks_preserves_existing_and_combines_sources(self):
        melde = parse_helper_payload(MELDEKARTE)
        first, merged, _, _ = create_or_merge(self.operation["id"], melde["data"], melde["source"])
        self.assertFalse(merged)
        drk = parse_helper_payload(DRK_AUSWEIS)
        drk["data"]["city"] = "Anderer Ort"
        second, merged, complemented, conflicts = create_or_merge(
            self.operation["id"], drk["data"], drk["source"]
        )
        self.assertTrue(merged)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["city"], "Musterstadt")
        self.assertEqual(second["membership_number"], "100200300")
        self.assertIn("membership_number", complemented)
        self.assertIn("city", {item["field"] for item in conflicts})
        self.assertEqual(second["sources"], ["Meldekarte-QR", "DRK-Server-QR"])
        self.assertEqual(second["source_category"], "Kombiniert")
        self.assertEqual(second["registered_at"], first["registered_at"])

    def test_duplicate_scope_is_per_operation(self):
        parsed = parse_helper_payload(MELDEKARTE)
        first, _, _, _ = create_or_merge(self.operation["id"], parsed["data"], parsed["source"])
        other_operation = add_operation("Andere Lage")
        second, merged, _, _ = create_or_merge(other_operation["id"], parsed["data"], parsed["source"])
        self.assertFalse(merged)
        self.assertNotEqual(first["id"], second["id"])


class HelperApiTests(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        project_root = os.path.dirname(os.path.dirname(__file__))
        app = Flask(
            __name__,
            template_folder=os.path.join(project_root, "templates"),
            static_folder=os.path.join(project_root, "static"),
        )
        app.config.update(TESTING=True)
        operation_overview.register(app, SocketIO(app))
        self.client = app.test_client()
        self.base = f"/api/operation_overview/{self.operation['id']}/helpers"

    def test_preview_create_list_status_and_delete(self):
        page = self.client.get(f"/operation_overview/{self.operation['id']}/helpers")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Helferregistrierung", page.data)
        self.assertIn(b"Anwesende Helfer", page.data)
        self.assertIn(b"Qualifikationen", page.data)
        self.assertNotIn(b"Besatzung", page.data)
        self.assertNotIn(b"<th>#</th>", page.data)
        self.assertNotIn(b"Verband / Gemeinschaft", page.data)
        self.assertNotIn(b"Alle Verb\xc3\xa4nde", page.data)
        self.assertIn(b"Alle Fahrzeuge", page.data)
        self.assertIn(b"Alle Qualifikationen", page.data)
        self.assertIn(b"Alle Status", page.data)
        self.assertIn(b"helper-modal__dialog--manual", page.data)

        preview = self.client.post(f"{self.base}/preview", json={"raw_payload": DRK_AUSWEIS})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.get_json()["source"], "DRK-Server-QR")

        created = self.client.post(self.base, json={
            "raw_payload": DRK_AUSWEIS,
            "data": preview.get_json()["data"],
        })
        self.assertEqual(created.status_code, 201)
        helper = created.get_json()["helper"]

        listing = self.client.get(self.base)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.get_json()["total"], 1)

        changed = self.client.patch(f"{self.base}/{helper['id']}", json={"status": "Abgemeldet"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.get_json()["status"], "Abgemeldet")
        deployment_end = changed.get_json()["deployment_end"]
        self.assertRegex(deployment_end, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

        unchanged_end = self.client.patch(
            f"{self.base}/{helper['id']}", json={"status": "Abgemeldet"}
        )
        self.assertEqual(unchanged_end.get_json()["deployment_end"], deployment_end)

        edited = self.client.patch(f"{self.base}/{helper['id']}", json={
            "first_name": "Robin",
            "gender": "w",
            "nutrition_type": "vegan",
            "mobile": "+49 170 7654321",
            "deployment_location": "Abschnitt B",
            "qualifications": ["ZF", "SAN"],
        })
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.get_json()["first_name"], "Robin")
        self.assertEqual(edited.get_json()["gender"], "w")
        self.assertEqual(edited.get_json()["nutrition_type"], "vegan")
        self.assertEqual(edited.get_json()["deployment_location"], "Abschnitt B")
        self.assertEqual(edited.get_json()["qualifications"], ["ZF", "SAN"])

        deleted = self.client.delete(f"{self.base}/{helper['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertIsNone(get_helper(helper["id"], self.operation["id"]))

    def test_manual_validation(self):
        response = self.client.post(self.base, json={"data": {"first_name": "Nur Vorname"}})
        self.assertEqual(response.status_code, 400)

    def test_list_returns_every_helper_without_pagination(self):
        for index in range(12):
            create_or_merge(self.operation["id"], {
                "last_name": f"Beispiel-{index:02d}",
                "first_name": "Alex",
                "birth_date": "1995-05-14",
            }, "Manuell")

        listing = self.client.get(f"{self.base}?page=1&page_size=3")
        self.assertEqual(listing.status_code, 200)
        payload = listing.get_json()
        self.assertEqual(payload["total"], 12)
        self.assertEqual(len(payload["items"]), 12)
        self.assertNotIn("pages", payload)

    def test_list_filters_by_vehicle_qualification_and_presence(self):
        qualified, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Qualifiziert",
            "first_name": "Alex",
            "birth_date": "1995-05-14",
            "qualifications": ["ZF", "SAN"],
        }, "Manuell")
        unassigned, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "OhneFahrzeug",
            "first_name": "Robin",
            "birth_date": "1990-03-20",
            "qualifications": ["SAN"],
        }, "Manuell")
        absent, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Abgemeldet",
            "first_name": "Kim",
            "birth_date": "1988-02-10",
            "qualifications": ["ZF"],
        }, "Manuell")
        vehicle = self.client.post(
            f"/api/operation_overview/{self.operation['id']}/vehicles",
            json={"call_sign": "Rotkreuz 1", "vehicle_type": "MTW", "target_occupancy": 1, "max_seats": 8},
        ).get_json()
        assigned = self.client.put(
            f"/api/operation_overview/{self.operation['id']}/vehicle-assignments/{qualified['id']}",
            json={"vehicle_id": vehicle["id"], "role": "member"},
        )
        self.assertEqual(assigned.status_code, 200)
        self.client.patch(f"{self.base}/{absent['id']}", json={"status": "Abgemeldet"})

        by_vehicle = self.client.get(f"{self.base}?vehicle={vehicle['id']}").get_json()
        self.assertEqual([item["id"] for item in by_vehicle["items"]], [qualified["id"]])

        unassigned_items = self.client.get(f"{self.base}?vehicle=unassigned").get_json()["items"]
        self.assertEqual({item["id"] for item in unassigned_items}, {unassigned["id"], absent["id"]})

        qualified_items = self.client.get(f"{self.base}?qualification=ZF").get_json()["items"]
        self.assertEqual({item["id"] for item in qualified_items}, {qualified["id"], absent["id"]})

        present_items = self.client.get(f"{self.base}?status=Anwesend").get_json()["items"]
        self.assertEqual({item["id"] for item in present_items}, {qualified["id"], unassigned["id"]})

    def test_search_includes_vehicle_qualification_and_gender(self):
        helper, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Suchbar",
            "first_name": "Alex",
            "birth_date": "1995-05-14",
            "gender": "d",
            "qualifications": ["NotSan"],
        }, "Manuell")
        vehicle = self.client.post(
            f"/api/operation_overview/{self.operation['id']}/vehicles",
            json={"call_sign": "Rotkreuz Wasser 7", "vehicle_type": "GW-Wasserrettung", "target_occupancy": 1, "max_seats": 6},
        ).get_json()
        self.client.put(
            f"/api/operation_overview/{self.operation['id']}/vehicle-assignments/{helper['id']}",
            json={"vehicle_id": vehicle["id"], "role": "member"},
        )

        for query in ("NotSan", "Notfallsanitäter", "Wasser 7", "GW-Wasserrettung", "Divers"):
            with self.subTest(query=query):
                items = self.client.get(self.base, query_string={"q": query}).get_json()["items"]
                self.assertEqual([item["id"] for item in items], [helper["id"]])

        all_items = self.client.get(self.base, query_string={"q": ""}).get_json()["items"]
        self.assertEqual([item["id"] for item in all_items], [helper["id"]])

    def test_statistics_count_gender_and_nutrition_only_for_present_helpers(self):
        present, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Anwesend",
            "first_name": "Alex",
            "birth_date": "1995-05-14",
            "gender": "m",
            "nutrition_type": "vegan",
        }, "Manuell")
        absent, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Abgemeldet",
            "first_name": "Robin",
            "birth_date": "1990-03-20",
            "gender": "w",
            "nutrition_type": "vegetarisch",
        }, "Manuell")
        response = self.client.patch(
            f"{self.base}/{absent['id']}", json={"status": "Abgemeldet"}
        )
        self.assertEqual(response.status_code, 200)

        payload = self.client.get(self.base).get_json()

        self.assertEqual(payload["stats"]["status"], {"Anwesend": 1, "Abgemeldet": 1})
        self.assertEqual(payload["stats"]["gender"]["m"], 1)
        self.assertEqual(payload["stats"]["gender"]["w"], 0)
        self.assertEqual(payload["stats"]["nutrition"]["vegan"], 1)
        self.assertEqual(payload["stats"]["nutrition"]["vegetarisch"], 0)


if __name__ == "__main__":
    unittest.main()
