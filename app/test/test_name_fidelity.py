import importlib
import unittest


try:
    portal = importlib.import_module("app.app")
except ModuleNotFoundError as exc:
    if exc.name != "app.app":
        raise
    portal = importlib.import_module("app")


ASSAMESE_NAME = "ৰূপা দাস"


class NameFidelityTest(unittest.TestCase):
    def test_sanitize_preserves_assamese_name_within_database_limit(self):
        self.assertEqual(portal.sanitize(ASSAMESE_NAME), ASSAMESE_NAME)

    def test_acknowledgment_embeds_unicode_name_font(self):
        class Cursor:
            def execute(self, *_args):
                pass

            def fetchone(self):
                return (
                    "SSP26123456", ASSAMESE_NAME, "0000000000", "1960-01-01",
                    "Sonapur", "Sonari", "000000000000", "ABCD0123456",
                    "2026-01-01", "PENDING",
                )

        pdf_bytes = portal.generate_acknowledgment(Cursor(), 1)
        self.assertTrue(b"NotoSansBengali" in pdf_bytes)
        self.assertTrue(b"/ToUnicode" in pdf_bytes)


if __name__ == "__main__":
    unittest.main()
