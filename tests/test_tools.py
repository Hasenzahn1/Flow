import os
import tempfile
import unittest

from flask import Flask

import core.db as core_db
from core.index_db import get_tools
from pages import auth, index


class ToolMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core_db.DB_PATH = os.path.join(self.tempdir.name, "test.db")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_color_migration_preserves_existing_tools(self):
        con = core_db.get_db()
        con.executescript(
            """
            CREATE TABLE tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                route TEXT NOT NULL,
                icon_path TEXT,
                order_index INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                description TEXT
            );
            INSERT INTO tools (label, route, icon_path, order_index, active, description)
            VALUES ('Bestand', '/bestand', 'grid', 3, 1, 'Bleibt erhalten');
            PRAGMA user_version = 3;
            """
        )
        con.commit()
        con.close()

        core_db.migrate()

        tool = get_tools(only_active=False)[0]
        self.assertEqual(tool["label"], "Bestand")
        self.assertEqual(tool["description"], "Bleibt erhalten")
        self.assertEqual(tool["color"], "blue")
        con = core_db.get_db()
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 7)
        self.assertIsNotNone(con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'overview_helper_qualifications'"
        ).fetchone())
        con.close()

    def test_new_database_starts_with_empty_catalog(self):
        core_db.init_db()
        core_db.migrate()
        self.assertEqual(get_tools(only_active=False), [])


class ToolFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        core_db.DB_PATH = os.path.join(self.tempdir.name, "test.db")
        core_db.init_db()
        core_db.migrate()

        project_root = os.path.dirname(os.path.dirname(__file__))
        self.app = Flask(
            __name__,
            template_folder=os.path.join(project_root, "templates"),
            static_folder=os.path.join(project_root, "static"),
        )
        self.app.config.update(TESTING=True, SECRET_KEY="tool-test-secret")
        auth.register(self.app)
        index.register(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def login(self):
        response = self.client.post("/api/auth/admin", json={"password": "admin"})
        self.assertEqual(response.status_code, 200)

    def create_tool(self, **overrides):
        payload = {
            "label": "Wetterkarte",
            "route": "/wetter",
            "description": "Aktuelle Wetterlage",
            "icon_path": "monitor",
            "color": "green",
            "active": True,
        }
        payload.update(overrides)
        return self.client.post("/api/tools", json=payload)

    def test_public_page_and_admin_api_permissions(self):
        page = self.client.get("/tools")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Keine weiteren Tools aktiviert", page.data)
        self.assertNotIn(b"Tools in den Einstellungen verwalten", page.data)
        self.assertEqual(self.client.get("/api/tools").status_code, 403)
        self.assertEqual(self.client.put("/api/tools/order", json={"tool_ids": []}).status_code, 403)

        self.login()
        admin_page = self.client.get("/tools")
        self.assertIn(b"Tools in den Einstellungen verwalten", admin_page.data)
        self.assertEqual(self.client.get("/api/tools").status_code, 200)
        settings = self.client.get("/settings")
        self.assertIn(b"Tool hinzuf", settings.data)
        self.assertIn(b"tool-settings.js", settings.data)

    def test_crud_rendering_and_home_count(self):
        self.login()
        internal = self.create_tool()
        self.assertEqual(internal.status_code, 201)
        internal_tool = internal.get_json()
        external = self.create_tool(
            label="Externe Karte",
            route="https://example.org/map",
            description="Externer Dienst",
            icon_path="grid",
            color="violet",
        )
        self.assertEqual(external.status_code, 201)
        external_tool = external.get_json()

        page = self.client.get("/tools")
        self.assertIn(b"Wetterkarte", page.data)
        self.assertIn(b"Externe Karte", page.data)
        self.assertIn(b'target="_blank" rel="noopener noreferrer"', page.data)
        self.assertIn(b"tool-card--violet", page.data)

        home = self.client.get("/")
        self.assertIn(b"<strong>2</strong> Tools aktiv", home.data)
        self.assertIn(b'href="/tools"', home.data)

        changed = self.client.put(
            f"/api/tools/{internal_tool['id']}",
            json={"label": "Wetter aktualisiert", "active": False},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.get_json()["active"], 0)
        page = self.client.get("/tools")
        self.assertNotIn(b"Wetter aktualisiert", page.data)
        self.assertIn(b"Externe Karte", page.data)
        self.assertIn(b"<strong>1</strong> Tool aktiv", self.client.get("/").data)

        deleted = self.client.delete(f"/api/tools/{external_tool['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.delete(f"/api/tools/{external_tool['id']}").status_code, 404)

    def test_validation_rejects_unsafe_or_unknown_values(self):
        self.login()
        invalid_routes = [
            "tools/foo",
            "//example.org/foo",
            "/\\example.org/foo",
            "javascript:alert(1)",
            "ftp://example.org",
        ]
        for route in invalid_routes:
            with self.subTest(route=route):
                self.assertEqual(self.create_tool(route=route).status_code, 400)

        self.assertEqual(self.create_tool(icon_path="unknown").status_code, 400)
        self.assertEqual(self.create_tool(color="purple").status_code, 400)
        self.assertEqual(self.create_tool(extra="field").status_code, 400)
        self.assertEqual(self.client.put("/api/tools/9999", json={"active": True}).status_code, 404)

    def test_reordering_requires_every_tool_exactly_once(self):
        self.login()
        first = self.create_tool(label="Erstes").get_json()
        second = self.create_tool(label="Zweites", route="/zwei").get_json()
        third = self.create_tool(label="Drittes", route="/drei").get_json()

        ordered_ids = [third["id"], first["id"], second["id"]]
        response = self.client.put("/api/tools/order", json={"tool_ids": ordered_ids})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([tool["id"] for tool in response.get_json()], ordered_ids)
        self.assertEqual([tool["id"] for tool in get_tools(only_active=False)], ordered_ids)

        for invalid in ([first["id"]], [first["id"], first["id"], third["id"]], ordered_ids + [9999]):
            with self.subTest(tool_ids=invalid):
                self.assertEqual(
                    self.client.put("/api/tools/order", json={"tool_ids": invalid}).status_code,
                    400,
                )


if __name__ == "__main__":
    unittest.main()
