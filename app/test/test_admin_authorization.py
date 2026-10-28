import importlib
import unittest
from unittest.mock import Mock, patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


FAKE_ID = 987654321


class AdminAuthorizationTest(unittest.TestCase):
    def post_as(self, path, session_values):
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session.update(session_values)
        connection = Mock()
        connection.cursor.return_value = Mock()
        with patch.object(portal, "get_db", return_value=connection) as get_db:
            response = client.post(path)
        return response, get_db, connection

    def test_citizen_cannot_approve_application(self):
        portal.app.config["TESTING"] = True
        response, get_db, _ = self.post_as(
            f"/admin/approve/{FAKE_ID}",
            {"logged_in": True, "portal_mobile": "0000000001"},
        )
        self.assertEqual(response.status_code, 403)
        get_db.assert_not_called()

    def test_citizen_cannot_reject_application(self):
        portal.app.config["TESTING"] = True
        response, get_db, _ = self.post_as(
            f"/admin/reject/{FAKE_ID}",
            {"logged_in": True, "portal_mobile": "0000000001"},
        )
        self.assertEqual(response.status_code, 403)
        get_db.assert_not_called()

    def test_admin_can_approve_application(self):
        portal.app.config["TESTING"] = True
        response, _, connection = self.post_as(
            f"/admin/approve/{FAKE_ID}",
            {"logged_in": True, "admin": True},
        )
        self.assertEqual(response.status_code, 302)
        connection.cursor.return_value.execute.assert_called_once()

    def test_admin_can_reject_application(self):
        portal.app.config["TESTING"] = True
        response, _, connection = self.post_as(
            f"/admin/reject/{FAKE_ID}",
            {"logged_in": True, "admin": True},
        )
        self.assertEqual(response.status_code, 302)
        connection.cursor.return_value.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
