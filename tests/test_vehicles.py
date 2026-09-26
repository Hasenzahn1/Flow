import json
import os
import tempfile
import unittest

from flask import Flask
from flask_socketio import SocketIO

import core.db as core_db
from core.operation_overview.helper_db import create_or_merge, get_helper, update_helper
from core.operation_overview.operation_db import add_operation
from core.operation_overview.vehicle_db import (
    VehiclePayloadError,
    assign_helper,
    create_vehicle,
    get_vehicle,
    list_vehicles,
    reorder_vehicles,
    update_vehicle,
)
from core.operation_overview import vehicle_templates
from tools.operation_overview import operation_overview


class VehicleTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core_db.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        vehicle_templates.TEMPLATE_DIR = os.path.join(self.tempdir.name, "vehicle_templates")
        core_db.init_db()
        core_db.migrate()
        self.operation = add_operation("Testlage")

    def tearDown(self):
        self.tempdir.cleanup()

    def helper(self, suffix, status="Anwesend"):
        helper, _, _, _ = create_or_merge(self.operation["id"], {
            "last_name": f"Beispiel-{suffix}",
            "first_name": "Alex",
            "birth_date": f"1990-01-{int(suffix) + 1:02d}",
        }, "Manuell")
        if status != "Anwesend":
            helper = update_helper(self.operation["id"], helper["id"], {"status": status})
        return helper

    def vehicle(self, call_sign="Rotkreuz 71/1", target=2, maximum=4):
        return create_vehicle(self.operation["id"], {
            "call_sign": call_sign,
            "vehicle_type": "RTW",
            "phone": "+49 123",
            "target_occupancy": target,
            "max_seats": maximum,
        })


class VehicleDatabaseTests(VehicleTestCase):
    def test_status_assignment_leader_and_overbooking(self):
        vehicle = self.vehicle()
        self.assertEqual(vehicle["status"], "Unbesetzt")
        helpers = [self.helper(str(index)) for index in range(5)]

        assign_helper(self.operation["id"], helpers[0]["id"], vehicle["id"], "leader")
        self.assertEqual(get_vehicle(self.operation["id"], vehicle["id"])["status"], "Unvollständig")
        assign_helper(self.operation["id"], helpers[1]["id"], vehicle["id"], "member")
        self.assertEqual(get_vehicle(self.operation["id"], vehicle["id"])["status"], "Gut besetzt")
        assign_helper(self.operation["id"], helpers[2]["id"], vehicle["id"], "member")
        assign_helper(self.operation["id"], helpers[3]["id"], vehicle["id"], "member")
        self.assertEqual(get_vehicle(self.operation["id"], vehicle["id"])["status"], "Voll")
        assign_helper(self.operation["id"], helpers[4]["id"], vehicle["id"], "member")
        overbooked = get_vehicle(self.operation["id"], vehicle["id"])
        self.assertEqual(overbooked["status"], "Überbelegt")
        self.assertEqual(overbooked["over_capacity_by"], 1)

    def test_exclusive_assignment_leader_replacement_and_absence(self):
        first_vehicle = self.vehicle("Rotkreuz 1")
        second_vehicle = self.vehicle("Rotkreuz 2")
        first = self.helper("1")
        second = self.helper("2")
        assign_helper(self.operation["id"], first["id"], first_vehicle["id"], "leader")
        assign_helper(self.operation["id"], second["id"], first_vehicle["id"], "leader")
        changed = get_vehicle(self.operation["id"], first_vehicle["id"])
        roles = {person["id"]: person["role"] for person in changed["crew"]}
        self.assertEqual(roles[first["id"]], "member")
        self.assertEqual(roles[second["id"]], "leader")

        assign_helper(self.operation["id"], first["id"], second_vehicle["id"], "member")
        self.assertNotIn(first["id"], {person["id"] for person in get_vehicle(
            self.operation["id"], first_vehicle["id"]
        )["crew"]})
        self.assertEqual(get_helper(first["id"], self.operation["id"])["vehicle_id"], second_vehicle["id"])

        update_helper(self.operation["id"], first["id"], {"status": "Abgemeldet"})
        self.assertIsNone(get_helper(first["id"], self.operation["id"])["vehicle_id"])

    def test_validation_reordering_and_operation_isolation(self):
        with self.assertRaises(VehiclePayloadError):
            create_vehicle(self.operation["id"], {
                "call_sign": "Fehler", "vehicle_type": "RTW",
                "target_occupancy": 3, "max_seats": 2,
            })
        first = self.vehicle("B")
        second = self.vehicle("A")
        self.assertTrue(reorder_vehicles(self.operation["id"], [second["id"], first["id"]]))
        self.assertEqual([item["call_sign"] for item in list_vehicles(self.operation["id"])["items"]], ["A", "B"])
        self.assertFalse(reorder_vehicles(self.operation["id"], [first["id"]]))

        other = add_operation("Andere Lage")
        helper = self.helper("3")
        with self.assertRaises(VehiclePayloadError):
            assign_helper(other["id"], helper["id"], first["id"], "member")

    def test_lowering_capacity_keeps_crew_and_warns(self):
        vehicle = self.vehicle(target=2, maximum=4)
        for index in range(3):
            helper = self.helper(str(index + 4))
            assign_helper(self.operation["id"], helper["id"], vehicle["id"], "leader" if index == 0 else "member")
        changed = update_vehicle(self.operation["id"], vehicle["id"], {"target_occupancy": 2, "max_seats": 2})
        self.assertEqual(changed["crew_count"], 3)
        self.assertEqual(changed["status"], "Überbelegt")


class VehicleTemplateTests(VehicleTestCase):
    def test_template_file_excludes_people_and_applies_both_modes(self):
        vehicle = self.vehicle()
        helper = self.helper("1")
        assign_helper(self.operation["id"], helper["id"], vehicle["id"], "leader")

        document, overwritten = vehicle_templates.save_template(self.operation["id"], "SEG Standard")
        self.assertFalse(overwritten)
        files = os.listdir(vehicle_templates.TEMPLATE_DIR)
        self.assertEqual(files, [f"{document['id']}.json"])
        with open(os.path.join(vehicle_templates.TEMPLATE_DIR, files[0]), encoding="utf-8") as file:
            raw = json.load(file)
        serialized = json.dumps(raw)
        self.assertNotIn("Alex", serialized)
        self.assertNotIn("helper", serialized.casefold())
        self.assertNotIn("crew", serialized.casefold())

        vehicle_templates.apply_template(document["id"], self.operation["id"], "append")
        self.assertEqual(list_vehicles(self.operation["id"])["total"], 2)
        vehicle_templates.apply_template(document["id"], self.operation["id"], "replace")
        result = list_vehicles(self.operation["id"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["crew"], [])
        self.assertIsNone(get_helper(helper["id"], self.operation["id"])["vehicle_id"])

    def test_duplicate_name_requires_overwrite_and_bad_file_is_reported(self):
        self.vehicle()
        document, _ = vehicle_templates.save_template(self.operation["id"], "Standard")
        with self.assertRaises(FileExistsError):
            vehicle_templates.save_template(self.operation["id"], "standard")
        overwritten, was_overwritten = vehicle_templates.save_template(
            self.operation["id"], "standard", overwrite=True
        )
        self.assertTrue(was_overwritten)
        self.assertEqual(overwritten["id"], document["id"])

        with open(os.path.join(vehicle_templates.TEMPLATE_DIR, "f" * 32 + ".json"), "w", encoding="utf-8") as file:
            file.write("not-json")
        listing = vehicle_templates.list_templates()
        self.assertEqual(sum(item.get("invalid", False) for item in listing), 1)


class VehicleApiTests(VehicleTestCase):
    def setUp(self):
        super().setUp()
        project_root = os.path.dirname(os.path.dirname(__file__))
        app = Flask(
            __name__, template_folder=os.path.join(project_root, "templates"),
            static_folder=os.path.join(project_root, "static"),
        )
        app.config.update(TESTING=True)
        operation_overview.register(app, SocketIO(app))
        self.client = app.test_client()
        self.base = f"/api/operation_overview/{self.operation['id']}"

    def test_pages_crud_assignment_and_no_pagination(self):
        page = self.client.get(f"/operation_overview/{self.operation['id']}/vehicles")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Fahrzeug\xc3\xbcbersicht", page.data)
        self.assertNotIn(b"pagination", page.data.lower())
        tools_page = self.client.get(f"/operation_overview/{self.operation['id']}")
        self.assertIn(b"Fahrzeug\xc3\xbcbersicht", tools_page.data)
        helpers_page = self.client.get(f"/operation_overview/{self.operation['id']}/helpers")
        self.assertIn(b"Fahrzeug", helpers_page.data)

        created = self.client.post(f"{self.base}/vehicles", json={
            "call_sign": "Rotkreuz Test 1", "vehicle_type": "RTW", "phone": None,
            "target_occupancy": 2, "max_seats": 4,
        })
        self.assertEqual(created.status_code, 201)
        vehicle = created.get_json()
        helper = self.helper("1")
        assigned = self.client.put(f"{self.base}/vehicle-assignments/{helper['id']}", json={
            "vehicle_id": vehicle["id"], "role": "leader",
        })
        self.assertEqual(assigned.status_code, 200)
        listing = self.client.get(f"{self.base}/vehicles?page=1&page_size=1").get_json()
        self.assertEqual(len(listing["items"]), 1)
        self.assertNotIn("pages", listing)
        self.assertEqual(listing["items"][0]["leader"]["id"], helper["id"])

        changed = self.client.patch(f"{self.base}/vehicles/{vehicle['id']}", json={"max_seats": 5})
        self.assertEqual(changed.get_json()["max_seats"], 5)
        deleted = self.client.delete(f"{self.base}/vehicles/{vehicle['id']}")
        self.assertEqual(deleted.status_code, 204)

    def test_template_api(self):
        self.vehicle()
        created = self.client.post("/api/vehicle-templates", json={
            "operation_id": self.operation["id"], "name": "API Vorlage",
        })
        self.assertEqual(created.status_code, 201)
        template_id = created.get_json()["id"]
        duplicate = self.client.post("/api/vehicle-templates", json={
            "operation_id": self.operation["id"], "name": "api vorlage",
        })
        self.assertEqual(duplicate.status_code, 409)
        applied = self.client.post(f"/api/vehicle-templates/{template_id}/apply", json={
            "operation_id": self.operation["id"], "mode": "append",
        })
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.get_json()["total"], 2)
        self.assertEqual(self.client.delete(f"/api/vehicle-templates/{template_id}").status_code, 204)


if __name__ == "__main__":
    unittest.main()
