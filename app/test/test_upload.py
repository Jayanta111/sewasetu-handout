import importlib
import io
import tempfile
import unittest
from unittest.mock import patch


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class UploadTest(unittest.TestCase):
    def setUp(self):
        portal.app.config["TESTING"] = True
        self.temp_upload_dir = tempfile.TemporaryDirectory()
        self.upload_dir_patch = patch.object(
            portal, "UPLOAD_DIR", self.temp_upload_dir.name
        )
        self.upload_dir_patch.start()

    def tearDown(self):
        self.upload_dir_patch.stop()
        self.temp_upload_dir.cleanup()

    def post_upload(self, filename, content):
        client = portal.app.test_client()
        with client.session_transaction() as session:
            session["verified_mobile"] = "0000000000"
        stream = io.BytesIO(content)
        try:
            response = client.post(
                "/upload",
                data={"document": (stream, filename)},
                content_type="multipart/form-data",
            )
        finally:
            stream.close()
        return client, response

    def test_accepts_jpeg(self):
        _, response = self.post_upload(
            "age-proof.jpg", b"\xff\xd8\xff\xe0" + b"fake-jpeg-data"
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/declaration"))

    def test_accepts_pdf_at_5_mb_limit(self):
        content = b"%PDF-1.7\n" + b"x" * (MAX_UPLOAD_BYTES - 9)
        _, response = self.post_upload("age-proof.pdf", content)
        self.assertEqual(len(content), MAX_UPLOAD_BYTES)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/declaration"))

    def test_rejects_file_over_5_mb_with_clear_message(self):
        content = b"%PDF-1.7\n" + b"x" * (MAX_UPLOAD_BYTES - 8)
        _, response = self.post_upload("age-proof.pdf", content)
        self.assertEqual(len(content), MAX_UPLOAD_BYTES + 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Maximum size is 5 MB", response.get_data(as_text=True))

    def test_rejects_unsupported_file_with_clear_message(self):
        _, response = self.post_upload("age-proof.gif", b"GIF89a")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Please upload a JPG or PDF file", response.get_data(as_text=True))

    def test_rejects_pdf_extension_with_non_pdf_content(self):
        _, response = self.post_upload("age-proof.pdf", b"not a PDF")
        self.assertEqual(response.status_code, 200)
        self.assertIn("valid PDF or JPG", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
