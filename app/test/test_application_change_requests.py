import importlib
import unittest
from unittest.mock import patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


FAKE_ID = 987654321
FAKE_MOBILE = "0000000001"


class RecordingCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def execute(self, query, *params):
        if len(params) == 1 and isinstance(params[0], tuple):
            params = params[0]
        self.calls.append((query, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def close(self):
        pass


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class ApplicationChangeRequestTest(unittest.TestCase):
    def setUp(self):
        portal.app.config["TESTING"] = False

    def test_owner_submits_correction_for_staff_review_without_direct_edit(self):
        cursor = RecordingCursor([
            (FAKE_MOBILE, "PENDING"),
            None,
            (54,),
        ])
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = FAKE_MOBILE

        with patch.object(
            portal, "get_db", return_value=RecordingConnection(cursor)
        ):
            response = client.post(
                f"/application/{FAKE_ID}/change-request",
                data={
                    "request_type": "CORRECTION",
                    "field_name": "applicant_name",
                    "proposed_value": "Fictional Corrected Name",
                    "details": "Age proof contains the corrected spelling.",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(any("INSERT INTO application_change_requests" in q
                            for q, _ in cursor.calls))
        self.assertFalse(any(q.lstrip().upper().startswith("UPDATE APPLICATIONS")
                             for q, _ in cursor.calls))

    def test_non_owner_cannot_request_application_change(self):
        cursor = RecordingCursor([(FAKE_MOBILE, "PENDING")])
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = "0000000002"

        with patch.object(
            portal, "get_db", return_value=RecordingConnection(cursor)
        ):
            response = client.post(
                f"/application/{FAKE_ID}/change-request",
                data={"request_type": "WITHDRAWAL", "details": "Mistake"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(cursor.calls), 1)

    def test_admin_approves_withdrawal_and_retains_application_row(self):
        cursor = RecordingCursor([
            (54, FAKE_ID, FAKE_MOBILE, "WITHDRAWAL", None, None, "OPEN",
             "PENDING", None),
        ])
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["admin"] = True

        with (
            patch.object(portal, "ADMIN_USERNAME", "unit-admin"),
            patch.object(portal, "get_db", return_value=RecordingConnection(cursor)),
        ):
            response = client.post(
                "/admin/change-request/54/review",
                data={"decision": "APPROVE", "review_notes": "Withdrawal approved"},
            )

        self.assertEqual(response.status_code, 302)
        sql = " ".join(query.upper() for query, _ in cursor.calls)
        self.assertIn("UPDATE APPLICATIONS SET STATUS = 'WITHDRAWN'", sql)
        self.assertIn("UPDATE APPLICATION_CHANGE_REQUESTS", sql)
        self.assertNotIn("DELETE FROM APPLICATIONS", sql)

    def test_admin_approves_correction_using_a_bound_value(self):
        cursor = RecordingCursor([
            (55, FAKE_ID, FAKE_MOBILE, "CORRECTION", "applicant_name",
             "Fictional Corrected Name", "OPEN", "PENDING", None),
        ])
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["admin"] = True

        with patch.object(
            portal, "get_db", return_value=RecordingConnection(cursor)
        ):
            response = client.post(
                "/admin/change-request/55/review",
                data={"decision": "APPROVE", "review_notes": "Checked document"},
            )

        self.assertEqual(response.status_code, 302)
        correction_updates = [call for call in cursor.calls
                              if call[0].startswith("UPDATE applications SET")]
        self.assertEqual(len(correction_updates), 1)
        self.assertIn("applicant_name = %s", correction_updates[0][0])
        self.assertEqual(correction_updates[0][1],
                         ("Fictional Corrected Name", FAKE_ID))

    def test_citizen_cannot_access_staff_review_queue(self):
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["logged_in"] = True
            session["portal_mobile"] = FAKE_MOBILE

        response = client.get("/admin/change-requests", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/admin"))


if __name__ == "__main__":
    unittest.main()
