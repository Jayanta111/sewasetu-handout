# -*- coding: utf-8 -*-
"""
Nightly deemed-approval job.

Under the Purvanchal Right to Public Services Act, an application not processed
within the statutory SLA stands approved. This job marks such applications
DEEMED_APPROVED and notifies the applicant by SMS.

Scheduled via cron, 02:00 daily. See deploy/crontab.
"""

import argparse
import os
import configparser
from datetime import datetime, timedelta

import psycopg2
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

config = configparser.ConfigParser()
CONFIG_PATH = os.path.join(BASE_DIR, "config", "app.ini")
with open(CONFIG_PATH) as fh:
    config.read_file(fh)

SLA_DAYS = config.getint("pension", "sla_days")
SMS_GATEWAY_URL = config.get("app", "sms_gateway_url")


def main(dry_run=False):
    conn = psycopg2.connect(
        host=config.get("database", "host"),
        port=config.get("database", "port"),
        dbname=os.environ.get(
            "SEWASETU_DB_NAME", config.get("database", "name")),
        user=config.get("database", "user"),
        password=os.environ["SEWASETU_DB_PASSWORD"],
    )
    cutoff = datetime.now() - timedelta(days=SLA_DAYS)

    if dry_run:
        # Enforce read-only mode at the database transaction level as well as
        # using a SELECT query. This path never sends applicant notifications.
        conn.set_session(readonly=True)
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT COUNT(*)
                   FROM applications
                   WHERE status = 'PENDING' AND submitted_at < %s""",
                (cutoff,))
            candidate_count = cur.fetchone()[0]
            print("%s DRY RUN: %d pending applications meet the %d-day SLA "
              "cutoff; no records changed and no SMS sent"
                  % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     candidate_count, SLA_DAYS))
            return candidate_count
        finally:
            cur.close()
            conn.close()

    cur = conn.cursor()
    cur.execute(
        """UPDATE applications
           SET status = 'DEEMED_APPROVED', decided_at = %s, decided_by = 'RTPS-AUTO'
           WHERE status = 'PENDING' AND submitted_at < %s
           RETURNING application_no, mobile""",
        (datetime.now(), cutoff))
    rows = cur.fetchall()
    conn.commit()
    for app_no, mobile in rows:
        try:
            requests.post(SMS_GATEWAY_URL + "/api/send", json={
                "to": mobile,
                "text": "Sewa Setu: your pension application %s stands approved "
                        "under the RTPS Act." % app_no}, timeout=5)
        except Exception:
            pass
    print("%s deemed approval: %d applications approved"
          % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(rows)))
    cur.close()
    conn.close()
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process RTPS deemed approvals")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="count eligible pending applications without changing rows or sending SMS")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
