import datetime
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
FAKE_OWNER = "0000000002"
FAKE_APPLICATION_ROW = (
    "SSP26TEST002",
    "Fictional Applicant",
    FAKE_OWNER,
    datetime.date(1950, 1, 1),
    "Demo Village",
    "Sonari",
    "000000000000",
    "TEST0000001",
    "PENDING",
    datetime.datetime(2026, 10, 28, 12, 0),
    None,
)


class ApplicationAuthorizationTest(unittest.TestCase):
    def client_for(self, mobile):
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = mobile
        return client

    def test_logged_in_applicant_cannot_view_another_applicant(self):
        cursor = Mock()
        cursor.fetchone.return_value = FAKE_APPLICATION_ROW
        connection = Mock()
        connection.cursor.return_value = cursor
        client = self.client_for("0000000001")

        with patch.object(portal, "get_db", return_value=connection):
            response = client.get(f"/application/{FAKE_ID}")

        self.assertEqual(response.status_code, 403)

    def test_logged_in_applicant_can_view_their_own_application(self):
        cursor = Mock()
        cursor.fetchone.return_value = FAKE_APPLICATION_ROW
        connection = Mock()
        connection.cursor.return_value = cursor
        client = self.client_for(FAKE_OWNER)

        with patch.object(portal, "get_db", return_value=connection):
            response = client.get(f"/application/{FAKE_ID}")

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
