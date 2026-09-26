import os
import tempfile
import unittest

from flask import Flask
from flask_socketio import SocketIO
from werkzeug.security import check_password_hash, generate_password_hash

import core.db as core_db
from core.auth import get_auth_settings
from pages import auth, index
from tools.operation_overview import operation_overview


class AuthFeatureTests(unittest.TestCase):
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
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
        )
        socketio = SocketIO(self.app)
        auth.register(self.app)
        index.register(self.app)
        operation_overview.register(self.app, socketio)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def login(self, client=None, password="admin"):
        return (client or self.client).post("/api/auth/admin", json={"password": password})

    def test_migration_seeds_hashed_password_and_preserves_changes(self):
        settings = get_auth_settings()
        self.assertNotEqual(settings["admin_password_hash"], "admin")
        self.assertTrue(check_password_hash(settings["admin_password_hash"], "admin"))

        custom_hash = generate_password_hash("custom-password")
        con = core_db.get_db()
        con.execute("UPDATE auth_settings SET admin_password_hash = ? WHERE id = 1", (custom_hash,))
        con.commit()
        con.close()

        core_db.init_db()
        core_db.migrate()
        self.assertEqual(get_auth_settings()["admin_password_hash"], custom_hash)

    def test_guest_is_default_and_configuration_is_hidden_and_protected(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b">Guest<", home.data)
        self.assertNotIn(b'href="/settings"', home.data)
        self.assertNotIn(b"/api/update/check", home.data)

        self.assertEqual(self.client.get("/api/tools").status_code, 403)
        self.assertEqual(self.client.get("/api/update/check").status_code, 403)
        self.assertEqual(self.client.post("/api/update/apply").status_code, 403)
        settings = self.client.get("/settings")
        self.assertEqual(settings.status_code, 302)
        self.assertEqual(settings.headers["Location"], "/")

        operational = self.client.post("/api/operation_overview", json={"name": "Gastlage"})
        self.assertEqual(operational.status_code, 201)

    def test_admin_login_visibility_and_session_cookie(self):
        rejected = self.login(password="wrong")
        self.assertEqual(rejected.status_code, 401)
        self.assertEqual(self.client.get("/api/tools").status_code, 403)

        accepted = self.login()
        self.assertEqual(accepted.status_code, 200)
        cookie = accepted.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Expires=", cookie)

        home = self.client.get("/")
        self.assertIn(b">Admin<", home.data)
        self.assertIn(b'href="/settings"', home.data)
        self.assertIn(b"/api/update/check", home.data)
        self.assertEqual(self.client.get("/settings").status_code, 200)
        self.assertEqual(self.client.get("/api/tools").status_code, 200)

    def test_switching_to_guest_clears_admin_access(self):
        self.assertEqual(self.login().status_code, 200)
        switched = self.client.post("/api/auth/guest")
        self.assertEqual(switched.status_code, 200)
        self.assertEqual(switched.get_json()["role"], "guest")
        self.assertEqual(self.client.get("/settings").status_code, 302)

    def test_password_change_validation_and_session_invalidation(self):
        other_client = self.app.test_client()
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.login(other_client).status_code, 200)

        wrong_current = self.client.put("/api/settings/admin-password", json={
            "current_password": "wrong",
            "new_password": "new-password",
            "confirmation": "new-password",
        })
        self.assertEqual(wrong_current.status_code, 400)

        too_short = self.client.put("/api/settings/admin-password", json={
            "current_password": "admin",
            "new_password": "short",
            "confirmation": "short",
        })
        self.assertEqual(too_short.status_code, 400)

        mismatch = self.client.put("/api/settings/admin-password", json={
            "current_password": "admin",
            "new_password": "new-password",
            "confirmation": "different-password",
        })
        self.assertEqual(mismatch.status_code, 400)

        changed = self.client.put("/api/settings/admin-password", json={
            "current_password": "admin",
            "new_password": "new-password",
            "confirmation": "new-password",
        })
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get("/settings").status_code, 200)
        self.assertNotIn(b"Standardpasswort", self.client.get("/settings").data)

        self.assertEqual(other_client.get("/settings").status_code, 302)
        fresh_client = self.app.test_client()
        self.assertEqual(self.login(fresh_client, "admin").status_code, 401)
        self.assertEqual(self.login(fresh_client, "new-password").status_code, 200)


if __name__ == "__main__":
    unittest.main()
