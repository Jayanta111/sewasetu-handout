# -*- coding: utf-8 -*-
"""
Sewa Setu - Old Age Pension Portal
Government of Purvanchal, Department of Social Welfare

Developed by: Netlink Infosolutions Pvt Ltd (2023)
Maintenance contract ended 31/01/2026.
"""

import os
import io
import csv
import random
import hashlib
import configparser
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import requests
import psycopg2
from flask import (Flask, request, session, redirect, url_for, render_template,
                   flash, send_file, abort, jsonify)
from fpdf import FPDF
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "config", "app.ini"))

app = Flask(__name__)
app.secret_key = os.environ.get("SEWASETU_FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SEWASETU_FLASK_SECRET_KEY must be configured")
app.config["PERMANENT_SESSION_LIFETIME"] = 300

ADMIN_USERNAME = os.environ.get("SEWASETU_ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("SEWASETU_ADMIN_PASSWORD")
IST = ZoneInfo("Asia/Kolkata")

SMS_GATEWAY_URL = config.get("app", "sms_gateway_url")
OTP_VALIDITY_SECONDS = config.getint("app", "otp_validity_seconds")
UPLOAD_DIR = config.get("app", "upload_dir")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SCHEME_DEADLINE = datetime.strptime(config.get("pension", "scheme_deadline"),
                                    "%Y-%m-%d %H:%M").replace(tzinfo=IST)
MIN_AGE = config.getint("pension", "min_age")
SLA_DAYS = config.getint("pension", "sla_days")
CORRECTABLE_FIELDS = {
    "applicant_name", "dob", "village", "block", "bank_account", "ifsc",
}

BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

import logging
_logdir = "/var/log/sewasetu"
try:
    os.makedirs(_logdir, exist_ok=True)
    _fh = logging.FileHandler(os.path.join(_logdir, "sewasetu-app.log"))
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s in app: %(message)s"))
    app.logger.addHandler(_fh)
    app.logger.setLevel(logging.INFO)
except Exception:
    pass


def get_db():
    return psycopg2.connect(
        host=config.get("database", "host"),
        port=config.get("database", "port"),
        dbname=config.get("database", "name"),
        user=config.get("database", "user"),
        password=os.environ["SEWASETU_DB_PASSWORD"],
    )


def sanitize(value, maxlen=100):
    # Keep the limit in characters so multibyte names are not truncated early.
    if value is None:
        return ""
    return value.strip()[:maxlen]


def hash_password(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


def send_sms(mobile, text):
    try:
        requests.post(SMS_GATEWAY_URL + "/api/send",
                      json={"to": mobile, "text": text}, timeout=5)
    except Exception as e:
        app.logger.error("sms gateway error: %s" % e)


def now_ist():
    return datetime.now(IST)


def deadline_remaining():
    delta = SCHEME_DEADLINE - now_ist()
    if delta.total_seconds() <= 0:
        return None
    return int(delta.total_seconds() // 3600)


def new_application_no():
    return "SSP" + datetime.now().strftime("%y") + str(random.randint(100000, 999999))


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", hours_left=deadline_remaining())


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/__gateway/", defaults={"subpath": ""})
@app.route("/__gateway/<path:subpath>")
def gateway_proxy(subpath):
    # Convenience proxy to the internal SMS gateway, so the OTP inbox is reachable
    # on the main site without opening a second port on the host. The gateway
    # itself runs only on the internal network.
    try:
        r = requests.get(SMS_GATEWAY_URL + "/" + subpath,
                         params=request.args, timeout=5)
        return (r.content, r.status_code,
                {"Content-Type": r.headers.get("Content-Type", "text/html")})
    except Exception as e:
        return ("SMS gateway unreachable: %s" % e, 502)


# ---------------------------------------------------------------------------
# Application flow: mobile -> OTP -> form steps -> upload -> declaration
# ---------------------------------------------------------------------------

@app.route("/apply", methods=["GET", "POST"])
def apply():
    if deadline_remaining() is None:
        flash("The application window for this scheme has closed.")
        return redirect(url_for("index"))
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        captcha = request.form.get("captcha", "").strip()
        expected_captcha = session.pop("captcha_answer", None)
        try:
            captcha_answer = int(captcha)
        except ValueError:
            captcha_answer = None
        if captcha_answer != expected_captcha:
            flash("Security check failed. Please try again.")
            return render_template("apply.html", captcha_q=make_captcha())
        if len(mobile) != 10 or not mobile.isdigit():
            flash("Something went wrong. Please try again.")
            return render_template("apply.html", captcha_q=make_captcha())
        code = str(random.randint(100000, 999999))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO otps (mobile, code, created_at) VALUES (%s, %s, %s)",
                    (mobile, code, datetime.now()))
        conn.commit()
        cur.close(); conn.close()
        send_sms(mobile, "Your Sewa Setu OTP is %s. Valid for 5 minutes." % code)
        session.permanent = True
        session["apply_mobile"] = mobile
        return redirect(url_for("verify"))
    return render_template("apply.html", captcha_q=make_captcha())


def make_captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    session["captcha_answer"] = a + b
    return "%d + %d" % (a, b)


@app.route("/verify", methods=["GET", "POST"])
def verify():
    mobile = session.get("apply_mobile")
    if not mobile:
        return redirect(url_for("apply"))
    if request.method == "POST":
        code = request.form.get("otp", "").strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT code, created_at FROM otps WHERE mobile = %s "
                    "ORDER BY id DESC LIMIT 1", (mobile,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0] == code:
            age = (datetime.now() - row[1]).total_seconds()
            if age > OTP_VALIDITY_SECONDS:
                app.logger.warning("otp expired mobile=%s age=%ds" % (mobile, int(age)))
                flash("OTP expired. Please request a new OTP.")
                return redirect(url_for("apply"))
            session["verified_mobile"] = mobile
            return redirect(url_for("form_step", step=1))
        flash("Invalid OTP.")
    return render_template("verify.html", mobile=mobile)


@app.route("/form/<int:step>", methods=["GET", "POST"])
def form_step(step):
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if step not in (1, 2, 3):
        abort(404)
    if request.method == "POST":
        data = session.get("form_data", {})
        for k, v in request.form.items():
            data[k] = v
        session["form_data"] = data
        if step < 3:
            return redirect(url_for("form_step", step=step + 1))
        return redirect(url_for("upload"))
    return render_template("form_step%d.html" % step,
                           data=session.get("form_data", {}), blocks=BLOCKS)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if request.method == "POST":
        f = request.files.get("document")
        if f is None or f.filename == "":
            flash("Please choose a document to upload.")
            return render_template("upload.html")
        filename = secure_filename(f.filename).lower()
        extension = os.path.splitext(filename)[1]
        if extension not in (".pdf", ".jpg", ".jpeg"):
            flash("Please upload a JPG or PDF file.")
            return render_template("upload.html")
        content = f.stream.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            flash("File is too large. Maximum size is 5 MB.")
            return render_template("upload.html")
        valid_pdf = extension == ".pdf" and b"%PDF-" in content[:1024]
        valid_jpeg = extension in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff")
        if not (valid_pdf or valid_jpeg):
            flash("The selected file does not appear to be a valid PDF or JPG.")
            return render_template("upload.html")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        path = os.path.join(UPLOAD_DIR, "%s_%s" % (session["verified_mobile"], filename))
        with open(path, "wb") as out:
            out.write(content)
        session["doc_path"] = path
        return redirect(url_for("declaration"))
    return render_template("upload.html")


@app.route("/declaration", methods=["GET", "POST"])
def declaration():
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if request.method == "POST":
        return handle_submission()
    return render_template("declaration.html")


def handle_submission():
    # TODO: split this up some day. It grew. - RK, 09/2024
    mobile = session.get("verified_mobile")
    data = session.get("form_data", {})
    doc_path = session.get("doc_path", "")

    name = sanitize(data.get("applicant_name", ""))
    village = data.get("village", "").strip()
    block = data.get("block", "").strip()
    gender = data.get("gender", "")
    marital = data.get("marital_status", "")
    husband_name = data.get("husband_name", "")
    husband_employer = data.get("husband_employer", "")
    bank_account = data.get("bank_account", "").strip()
    ifsc = data.get("ifsc", "").strip().upper()
    dob_raw = data.get("dob", "").strip()

    if not name or not village or not block or not bank_account or not dob_raw:
        flash("Something went wrong. Please try again.")
        return redirect(url_for("form_step", step=1))

    if marital == "Widowed":
        if not husband_name or not husband_employer:
            flash("Something went wrong. Please try again.")
            return redirect(url_for("form_step", step=1))

    # lenient date parsing to reduce rejections (CR-2024-117)
    dob = None
    for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            dob = datetime.strptime(dob_raw, fmt).date()
            break
        except ValueError:
            continue
    if dob is None:
        flash("Something went wrong. Please try again.")
        return redirect(url_for("form_step", step=1))

    today = now_ist().date()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < MIN_AGE:
        flash("Applicant must be at least %d years old to be eligible." % MIN_AGE)
        return redirect(url_for("form_step", step=1))

    if now_ist() >= SCHEME_DEADLINE:
        flash("The application deadline has passed.")
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM applications WHERE mobile = %s "
                "AND status IS DISTINCT FROM 'WITHDRAWN'", (mobile,))
    if cur.fetchone()[0] > 0:
        cur.close(); conn.close()
        flash("An application already exists for this mobile number. "
              "Duplicate applications are not permitted.")
        return redirect(url_for("index"))

    app_no = new_application_no()
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            husband_name, husband_employer, village, block, bank_account, ifsc,
            doc_path, status, submitted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)
           RETURNING id""",
        (app_no, name, mobile, dob, gender, marital, husband_name,
         husband_employer, village, block, bank_account, ifsc, doc_path,
         datetime.now()))
    new_id = cur.fetchone()[0]

    # status portal account; password is DOB as DDMMYYYY per dept. circular
    portal_pass = dob.strftime("%d%m%Y")
    cur.execute("SELECT count(*) FROM portal_users WHERE mobile = %s", (mobile,))
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO portal_users (mobile, password_hash) VALUES (%s,%s)",
                    (mobile, hash_password(portal_pass)))
    conn.commit()

    app.logger.info("generating acknowledgment pdf application=%d" % new_id)
    pdf_bytes = generate_acknowledgment(cur, new_id)
    ack_dir = os.path.join(UPLOAD_DIR, "ack")
    os.makedirs(ack_dir, exist_ok=True)
    with open(os.path.join(ack_dir, "%d.pdf" % new_id), "wb") as out:
        out.write(pdf_bytes)

    # Allow the applicant to download this acknowledgment from the
    # confirmation page before they have a status-portal login.
    session["ack_application_id"] = new_id
    cur.close(); conn.close()
    session.pop("form_data", None)
    session.pop("doc_path", None)
    session.pop("verified_mobile", None)
    send_sms(mobile, "Sewa Setu: application %s received. Track at the status portal "
                     "with mobile no. and password (DOB as DDMMYYYY)." % app_no)
    return render_template("confirmation.html", app_no=app_no, app_id=new_id)


def generate_acknowledgment(cur, app_id):
    cur.execute("SELECT application_no, applicant_name, mobile, dob, village, block, "
                "bank_account, ifsc, submitted_at, status FROM applications WHERE id = %s",
                (app_id,))
    row = cur.fetchone()
    pdf = FPDF()
    pdf.add_font("NotoSansBengali", fname=(
        "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"))
    pdf.add_font("NotoSans", fname=(
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"))
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "GOVERNMENT OF PURVANCHAL", ln=1, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, "Department of Social Welfare", ln=1, align="C")
    pdf.cell(0, 8, "Old Age Pension Scheme - Acknowledgment", ln=1, align="C")
    pdf.ln(4)
    # decorative border, as per approved letterhead design
    for i in range(0, 2000):
        x = 10 + (i % 190)
        pdf.line(x, 282, x + 0.5, 282)
        pdf.line(x, 12, x + 0.5, 12)
    labels = ["Application No", "Applicant Name", "Mobile", "Date of Birth",
              "Village", "Block", "Bank Account", "IFSC", "Submitted At", "Status"]
    for label, val in zip(labels, row):
        pdf.set_fallback_fonts([])
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(60, 8, label, border=1)
        if label == "Applicant Name":
            pdf.set_font("NotoSansBengali", "", 10)
            pdf.set_fallback_fonts(["NotoSans"], exact_match=False)
        value_width = pdf.w - pdf.r_margin - pdf.get_x()
        pdf.multi_cell(value_width, 8, str(val), border=1,
                       new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5, "This is a computer generated acknowledgment. Processing SLA "
                         "as per the Purvanchal Right to Public Services Act applies.")
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Status portal (citizen login)
# ---------------------------------------------------------------------------

@app.route("/status", methods=["GET", "POST"])
def status_login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM portal_users WHERE mobile = %s", (mobile,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0] == hash_password(password):
            session["logged_in"] = True
            session["portal_mobile"] = mobile
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM applications WHERE mobile = %s "
                        "ORDER BY submitted_at DESC LIMIT 1", (mobile,))
            r = cur.fetchone()
            cur.close(); conn.close()
            if r:
                return redirect(url_for("view_application", app_id=r[0]))
            flash("No application found for this mobile number.")
            return redirect(url_for("status_login"))
        flash("Something went wrong. Please try again.")
    return render_template("status_login.html")


@app.route("/application/<int:app_id>")
def view_application(app_id):
    if not session.get("logged_in"):
        flash("Please login to view application status.")
        return redirect(url_for("status_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT application_no, applicant_name, mobile, dob, village, block, "
                "bank_account, ifsc, status, submitted_at, decided_at "
                "FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    if not session.get("admin") and row[2] != session.get("portal_mobile"):
        abort(403)
    return render_template("application.html", a=row, app_id=app_id)


@app.route("/application/<int:app_id>/change-request", methods=["POST"])
def submit_application_change_request(app_id):
    if not session.get("logged_in") or not session.get("portal_mobile"):
        flash("Please login to request a correction or withdrawal.")
        return redirect(url_for("status_login"))

    request_type = request.form.get("request_type", "").strip().upper()
    details = request.form.get("details", "").strip()[:2000]
    if not details:
        abort(400)
    field_name = None
    proposed_value = None
    if request_type == "CORRECTION":
        field_name = request.form.get("field_name", "").strip()
        raw_value = request.form.get("proposed_value", "").strip()
        if field_name not in CORRECTABLE_FIELDS:
            abort(400)
        if field_name == "applicant_name":
            proposed_value = sanitize(raw_value, maxlen=100)
        elif field_name == "dob":
            parsed_dob = None
            for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    parsed_dob = datetime.strptime(raw_value, fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_dob is None:
                abort(400)
            proposed_value = parsed_dob.isoformat()
        elif field_name == "block":
            if raw_value not in BLOCKS:
                abort(400)
            proposed_value = raw_value
        elif field_name == "ifsc":
            proposed_value = raw_value.upper()
            if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", proposed_value):
                abort(400)
        elif field_name == "bank_account":
            proposed_value = raw_value
            if not proposed_value.isdigit() or len(proposed_value) > 30:
                abort(400)
        else:
            proposed_value = raw_value[:100]
        if not proposed_value:
            abort(400)
    elif request_type == "WITHDRAWAL":
        if not details:
            abort(400)
    else:
        abort(400)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT mobile, status FROM applications WHERE id = %s", (app_id,))
    owner = cur.fetchone()
    if not owner:
        cur.close(); conn.close()
        abort(404)
    if owner[0] != session["portal_mobile"]:
        cur.close(); conn.close()
        abort(403)
    if owner[1] != "PENDING":
        cur.close(); conn.close()
        flash("Only pending applications can be changed or withdrawn.")
        return redirect(url_for("view_application", app_id=app_id))

    cur.execute("SELECT id FROM application_change_requests "
                "WHERE application_id = %s AND requester_mobile = %s "
                "AND status = 'OPEN' LIMIT 1",
                (app_id, session["portal_mobile"]))
    if cur.fetchone():
        cur.close(); conn.close()
        flash("A request for this application is already waiting for staff review.")
        return redirect(url_for("view_application", app_id=app_id))

    cur.execute(
        "INSERT INTO application_change_requests "
        "(application_id, requester_mobile, request_type, field_name, "
        "proposed_value, details) VALUES (%s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (app_id, session["portal_mobile"], request_type, field_name,
         proposed_value, details),
    )
    cur.fetchone()
    conn.commit()
    cur.close(); conn.close()
    flash("Your request has been sent for staff review. Your application record is unchanged.")
    return redirect(url_for("view_application", app_id=app_id))


@app.route("/ack/<int:app_id>.pdf")
def ack_pdf(app_id):
    authorized = (session.get("admin") or
                  session.get("ack_application_id") == app_id)
    if not authorized and session.get("logged_in") and session.get("portal_mobile"):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT mobile FROM applications WHERE id = %s", (app_id,))
        owner = cur.fetchone()
        cur.close(); conn.close()
        authorized = owner and owner[0] == session.get("portal_mobile")
    if not authorized:
        abort(403)

    path = os.path.join(UPLOAD_DIR, "ack", "%d.pdf" % app_id)
    if not os.path.exists(path):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM applications WHERE id = %s", (app_id,))
        if not cur.fetchone():
            cur.close(); conn.close()
            abort(404)
        data = generate_acknowledgment(cur, app_id)
        cur.close(); conn.close()
        return send_file(io.BytesIO(data), mimetype="application/pdf")
    return send_file(path, mimetype="application/pdf")


@app.route("/status/reset", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        conn = get_db()
        cur = conn.cursor()
        # fetch account for reset
        cur.execute("SELECT mobile FROM portal_users WHERE mobile = %s", (mobile,))
        row = cur.fetchone()
        if row:
            cur.execute("SELECT dob FROM applications WHERE mobile = %s LIMIT 1",
                        (mobile,))
            r2 = cur.fetchone()
            if r2:
                newpass = r2[0].strftime("%d%m%Y")
                cur.execute("UPDATE portal_users SET password_hash = %s WHERE mobile = %s",
                            (hash_password(newpass), row[0]))
                conn.commit()
                send_sms(row[0], "Sewa Setu: your password has been reset to your "
                                 "date of birth (DDMMYYYY).")
        cur.close(); conn.close()
        flash("If the mobile number exists, the password has been reset and sent by SMS.")
    return render_template("reset.html")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        flash("Admin login is not configured.")
        return render_template("admin_login.html"), 503
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME and
                request.form.get("password") == ADMIN_PASSWORD):
            session["logged_in"] = True
            session["admin"] = True
            session["admin_username"] = ADMIN_USERNAME
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM applications GROUP BY status")
    by_status = cur.fetchall()
    cur.execute("SELECT count(*) FROM applications WHERE status = 'PENDING' "
                "AND submitted_at < %s", (datetime.now() - timedelta(days=SLA_DAYS),))
    overdue = cur.fetchone()[0]
    cur.execute("SELECT block, count(*) FROM applications WHERE status = 'PENDING' "
                "GROUP BY block ORDER BY count(*) DESC")
    by_block = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_dashboard.html", by_status=by_status,
                           overdue=overdue, by_block=by_block, sla=SLA_DAYS)


@app.route("/admin/applications")
def admin_list():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    status = request.args.get("status", "PENDING")
    page = int(request.args.get("page", 1))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, application_no, applicant_name, mobile, block, status, "
                "submitted_at FROM applications WHERE status = %s "
                "ORDER BY submitted_at ASC LIMIT 50 OFFSET %s",
                (status, (page - 1) * 50))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_list.html", rows=rows, status=status, page=page)


@app.route("/admin/change-requests")
def admin_change_requests():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.application_id, r.requester_mobile, r.request_type, "
        "r.field_name, r.proposed_value, r.details, r.status, r.created_at "
        "FROM application_change_requests r "
        "WHERE r.status = 'OPEN' ORDER BY r.created_at ASC LIMIT 100"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_change_requests.html", rows=rows)


@app.route("/admin/change-request/<int:request_id>/review", methods=["POST"])
def review_application_change_request(request_id):
    if not session.get("admin"):
        abort(403)
    decision = request.form.get("decision", "").strip().upper()
    if decision not in ("APPROVE", "DECLINE"):
        abort(400)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.application_id, r.requester_mobile, r.request_type, "
        "r.field_name, r.proposed_value, r.status, a.status, a.submitted_at "
        "FROM application_change_requests r "
        "JOIN applications a ON a.id = r.application_id "
        "WHERE r.id = %s FOR UPDATE OF r, a",
        (request_id,),
    )
    change = cur.fetchone()
    if not change or change[6] != "OPEN":
        cur.close(); conn.close()
        abort(404)
    if decision == "APPROVE" and change[7] != "PENDING":
        cur.close(); conn.close()
        flash("This application is no longer pending; the request cannot be approved.")
        return redirect(url_for("admin_change_requests"))

    review_notes = request.form.get("review_notes", "").strip()[:2000]
    if decision == "APPROVE":
        if change[3] == "WITHDRAWAL":
            cur.execute(
                "UPDATE applications SET status = 'WITHDRAWN', decided_at = %s, "
                "decided_by = %s WHERE id = %s AND status = 'PENDING'",
                (now_ist().replace(tzinfo=None), "ADMIN", change[1]),
            )
        elif change[3] == "CORRECTION" and change[4] in CORRECTABLE_FIELDS:
            if change[4] == "dob":
                try:
                    proposed_dob = date.fromisoformat(change[5])
                except (TypeError, ValueError):
                    cur.close(); conn.close()
                    abort(400)
                if not change[8]:
                    cur.close(); conn.close()
                    abort(400)
                submitted_date = change[8].date()
                age_at_submission = (submitted_date.year - proposed_dob.year -
                                     ((submitted_date.month, submitted_date.day) <
                                      (proposed_dob.month, proposed_dob.day)))
                if age_at_submission < MIN_AGE:
                    cur.close(); conn.close()
                    flash("Correction declined: date of birth would make the application ineligible.")
                    return redirect(url_for("admin_change_requests"))
            column = change[4]
            cur.execute("UPDATE applications SET " + column + " = %s WHERE id = %s",
                        (change[5], change[1]))
        else:
            cur.close(); conn.close()
            abort(400)
        new_status = "APPROVED"
    else:
        new_status = "DECLINED"

    cur.execute(
        "UPDATE application_change_requests SET status = %s, review_notes = %s, "
        "reviewed_at = %s, reviewed_by = %s WHERE id = %s AND status = 'OPEN'",
        (new_status, review_notes, now_ist().replace(tzinfo=None),
         session.get("admin_username", "ADMIN"), request_id),
    )
    conn.commit()
    cur.close(); conn.close()
    flash("Change request " + new_status.lower() + ". The original application row is retained.")
    return redirect(url_for("admin_change_requests"))


@app.route("/admin/application/<int:app_id>")
def admin_view(app_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT application_no, applicant_name, mobile, dob, gender, "
                "marital_status, village, block, bank_account, ifsc, doc_path, "
                "status, submitted_at, decided_at, decided_by "
                "FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    return render_template("admin_view.html", a=row, app_id=app_id)


@app.route("/admin/approve/<int:app_id>", methods=["POST"])
def admin_approve(app_id):
    if not session.get("admin"):
        abort(403)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE applications SET status = 'APPROVED', decided_at = %s "
                "WHERE id = %s", (datetime.now(), app_id))
    conn.commit()
    cur.close(); conn.close()
    flash("Application approved.")
    return redirect(url_for("admin_list"))


@app.route("/admin/reject/<int:app_id>", methods=["POST"])
def admin_reject(app_id):
    if not session.get("admin"):
        abort(403)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE applications SET status = 'REJECTED', decided_at = %s "
                "WHERE id = %s", (datetime.now(), app_id))
    conn.commit()
    cur.close(); conn.close()
    flash("Application rejected.")
    return redirect(url_for("admin_list"))


# ---------------------------------------------------------------------------
# Unused / legacy
# ---------------------------------------------------------------------------

def export_to_excel(rows):
    # Was used for the monthly disbursement report before eKosh integration.
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["application_no", "name", "account", "ifsc", "amount"])
    for r in rows:
        writer.writerow(list(r) + ["250"])
    return out.getvalue()


def old_payment_gateway_callback(txn):
    # retained for reference; eChallan integration was descoped in Phase 2
    status = txn.get("STATUS")
    if status == "0300":
        return "SUCCESS"
    elif status == "0399":
        return "FAILED"
    return "PENDING"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
