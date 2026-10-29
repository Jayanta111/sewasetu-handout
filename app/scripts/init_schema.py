"""Initialize an empty deployment database before starting the web server."""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from app import get_db  # noqa: E402


def main():
    schema_path = APP_DIR / "schema.sql"
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.applications'), "
                "to_regclass('public.portal_users'), "
                "to_regclass('public.otps'), "
                "to_regclass('public.application_change_requests')"
            )
            tables = cursor.fetchone()
            if all(tables):
                print("Database schema is already initialized.", flush=True)
            elif any(tables):
                raise RuntimeError(
                    "Database schema is incomplete. Initialize it manually "
                    "from app/schema.sql before deploying."
                )
            else:
                cursor.execute(schema_path.read_text(encoding="utf-8"))
                conn.commit()
                print("Initialized empty database from app/schema.sql.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
