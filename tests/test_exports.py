import io
import os
import tempfile
import unittest
import zipfile

from flask import Flask
from flask_socketio import SocketIO

import core.db as core_db
from core.operation_overview.helper_db import create_or_merge, update_helper
from core.operation_overview.mission_db import add_mission
from core.operation_overview.operation_db import add_operation
from core.operation_overview.person_db import add_person
from core.operation_overview.vehicle_db import assign_helper, create_vehicle
from tools.operation_overview import operation_overview


class ExportApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core_db.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        core_db.init_db()
        core_db.migrate()
        self.operation = add_operation("Übung Main & Nord")

        project_root = os.path.dirname(os.path.dirname(__file__))
        app = Flask(
            __name__, template_folder=os.path.join(project_root, "templates"),
            static_folder=os.path.join(project_root, "static"),
        )
        app.config.update(TESTING=True)
        operation_overview.register(app, SocketIO(app))
        self.client = app.test_client()
        self.base = f"/api/operation_overview/{self.operation['id']}/export"

        mission = add_mission(self.operation["id"], "Abschnitt Nord", "RTW 1", "Test")
        add_person(mission["id"], "Patient", "Paula", None, "w", "Klinik", "Stabil")

        self.present, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Müller",
            "first_name": "Alex",
            "birth_date": "1990-01-02",
            "gender": "d",
            "mobile": "+49 170 123",
            "nutrition_type": "vegan",
            "deployment_location": "Abschnitt Nord",
            "membership_number": "M-100",
            "district_association_raw": "4090000 Kreisverband Test",
            "card_number": "K-200",
            "verification_code": "prüf-300",
            "qualifications": ["ZF", "SAN"],
        }, "Manuell")
        absent, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": "Abgemeldet",
            "first_name": "Robin",
            "birth_date": "1988-02-03",
            "gender": "w",
            "nutrition_type": "vegetarisch",
        }, "Manuell")
        update_helper(self.operation["id"], absent["id"], {"status": "Abgemeldet"})

        vehicle = create_vehicle(self.operation["id"], {
            "call_sign": "Rotkreuz 71/1",
            "vehicle_type": "RTW",
            "phone": "+49 931 123",
            "target_occupancy": 2,
            "max_seats": 4,
        })
        assign_helper(self.operation["id"], self.present["id"], vehicle["id"], "leader")

    def tearDown(self):
        self.tempdir.cleanup()

    def assert_pdf(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF-"))
        self.assertGreater(len(response.data), 1000)

    def test_default_and_each_section_return_pdf(self):
        self.assert_pdf(self.client.get(self.base))
        for section in ("patients", "helpers_summary", "helpers_detail", "vehicles"):
            with self.subTest(section=section):
                self.assert_pdf(self.client.get(
                    self.base, query_string={"section": section, "bundle": "pdf"}
                ))

    def test_combined_pdf_and_zip_bundle(self):
        query = [
            ("section", "patients"),
            ("section", "helpers_summary"),
            ("section", "helpers_detail"),
            ("section", "vehicles"),
        ]
        combined = self.client.get(self.base, query_string=[*query, ("bundle", "pdf")])
        self.assert_pdf(combined)
        self.assertIn("Gesamt", combined.headers["Content-Disposition"])

        zipped = self.client.get(self.base, query_string=[*query, ("bundle", "zip")])
        self.assertEqual(zipped.status_code, 200)
        self.assertEqual(zipped.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(zipped.data)) as archive:
            self.assertEqual(archive.namelist(), [
                "Patienten.pdf",
                "Helfer_Uebersicht.pdf",
                "Helfer_Detail.pdf",
                "Fahrzeuge.pdf",
            ])
            for filename in archive.namelist():
                self.assertTrue(archive.read(filename).startswith(b"%PDF-"))

    def test_export_validation_and_missing_operation(self):
        self.assertEqual(self.client.get(self.base, query_string={"bundle": "pdf"}).status_code, 400)
        self.assertEqual(self.client.get(
            self.base, query_string={"section": "unknown", "bundle": "pdf"}
        ).status_code, 400)
        self.assertEqual(self.client.get(
            self.base, query_string={"section": "patients", "bundle": "tar"}
        ).status_code, 400)
        self.assertEqual(self.client.get(
            "/api/operation_overview/999999/export"
        ).status_code, 404)

    def test_export_controls_are_rendered(self):
        overview = self.client.get("/operation_overview")
        self.assertIn(b"Lage exportieren", overview.data)
        self.assertIn(b"Als Gesamt-PDF exportieren", overview.data)
        self.assertIn(b"helpers_detail", overview.data)

        helpers = self.client.get(f"/operation_overview/{self.operation['id']}/helpers")
        self.assertIn(b"PDF exportieren", helpers.data)
        self.assertIn(b"helpers_summary", helpers.data)
        self.assertNotIn(b':readonly="!editingId"', helpers.data)


if __name__ == "__main__":
    unittest.main()
