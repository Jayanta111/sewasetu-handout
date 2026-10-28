import importlib
import unittest
from unittest.mock import patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


class AdminLoginTest(unittest.TestCase):
    def test_login_fails_closed_when_credentials_are_missing(self):
        portal.app.config["TESTING"] = True
        client = portal.app.test_client()

        with (
            patch.object(portal, "ADMIN_USERNAME", None),
            patch.object(portal, "ADMIN_PASSWORD", None),
        ):
            response = client.post(
                "/admin", data={"username": "any", "password": "any"}
            )

        self.assertEqual(response.status_code, 503)

    def test_valid_admin_login_sets_admin_session(self):
        portal.app.config["TESTING"] = True
        client = portal.app.test_client()

        with (
            patch.object(portal, "ADMIN_USERNAME", "unit-admin"),
            patch.object(portal, "ADMIN_PASSWORD", "unit-test-only"),
        ):
            response = client.post(
                "/admin",
                data={"username": "unit-admin", "password": "unit-test-only"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin/dashboard"))
        with client.session_transaction() as session:
            self.assertTrue(session.get("logged_in"))
            self.assertTrue(session.get("admin"))

    def test_dashboard_redirects_without_admin_session(self):
        response = portal.app.test_client().get(
            "/admin/dashboard", follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin"))


if __name__ == "__main__":
    unittest.main()
