import datetime
import importlib
import tempfile
import unittest
from unittest.mock import Mock, patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


FAKE_ID = 987654321
FAKE_MOBILE = "0000000000"
FAKE_APPLICATION_ROW = (
    "SSP26TEST001",
    "Test Applicant",
    FAKE_MOBILE,
    datetime.date(1950, 1, 1),
    "Demo Village",
    "Sonari",
    "000000000000",
    "TEST0000001",
    datetime.datetime(2026, 10, 28, 12, 0),
    "PENDING",
)


class AcknowledgmentAuthorizationTest(unittest.TestCase):
    def setUp(self):
        portal.app.config["TESTING"] = True
        self.upload_dir = tempfile.TemporaryDirectory()
        self.upload_patch = patch.object(portal, "UPLOAD_DIR", self.upload_dir.name)
        self.upload_patch.start()

    def tearDown(self):
        self.upload_patch.stop()
        self.upload_dir.cleanup()

    def test_anonymous_user_cannot_fetch_an_acknowledgment(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(FAKE_ID,), FAKE_APPLICATION_ROW]
        connection = Mock()
        connection.cursor.return_value = cursor

        with patch.object(portal, "get_db", return_value=connection):
            response = portal.app.test_client().get(f"/ack/{FAKE_ID}.pdf")

        self.assertEqual(response.status_code, 403)

    def test_logged_in_owner_can_fetch_their_acknowledgment(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [
            (FAKE_MOBILE,),
            (FAKE_ID,),
            FAKE_APPLICATION_ROW,
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = FAKE_MOBILE

        with patch.object(portal, "get_db", return_value=connection):
            response = client.get(f"/ack/{FAKE_ID}.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_logged_in_non_owner_cannot_fetch_an_acknowledgment(self):
        cursor = Mock()
        cursor.fetchone.return_value = ("0000000002",)
        connection = Mock()
        connection.cursor.return_value = cursor
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = "0000000001"

        with patch.object(portal, "get_db", return_value=connection):
            response = client.get(f"/ack/{FAKE_ID}.pdf")

        self.assertEqual(response.status_code, 403)

    def test_just_submitted_applicant_can_fetch_their_acknowledgment(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(FAKE_ID,), FAKE_APPLICATION_ROW]
        connection = Mock()
        connection.cursor.return_value = cursor
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["ack_application_id"] = FAKE_ID

        with patch.object(portal, "get_db", return_value=connection):
            response = client.get(f"/ack/{FAKE_ID}.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    def test_submission_session_is_authorized_for_its_acknowledgment(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(0,), (FAKE_ID,), (0,)]
        connection = Mock()
        connection.cursor.return_value = cursor
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["verified_mobile"] = FAKE_MOBILE
            session["form_data"] = {
                "applicant_name": "Test Applicant",
                "village": "Demo Village",
                "block": "Sonari",
                "bank_account": "000000000000",
                "ifsc": "TEST0000001",
                "dob": "01/01/1950",
                "marital_status": "Unmarried",
            }
            session["doc_path"] = "fictional-proof.pdf"

        future_deadline = (datetime.datetime.now(portal.IST)
                           + datetime.timedelta(days=1))
        with (
            patch.object(portal, "UPLOAD_DIR", self.upload_dir.name),
            patch.object(portal, "SCHEME_DEADLINE", future_deadline),
            patch.object(portal, "get_db", return_value=connection),
            patch.object(portal, "new_application_no", return_value="SSP26TEST001"),
            patch.object(portal, "generate_acknowledgment", return_value=b"%PDF-test"),
            patch.object(portal, "send_sms"),
            patch.object(portal.app.logger, "info"),
        ):
            response = client.post("/declaration")

        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            self.assertEqual(session.get("ack_application_id"), FAKE_ID)


if __name__ == "__main__":
    unittest.main()
