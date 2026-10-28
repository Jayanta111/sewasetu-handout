# Sewa Setu Investigation Kanban

**Scope:** DC briefing, repository inspection, Jan–Jun 2026 logs, and work completed in this workspace. Personal citizen data is excluded.

**Status key:** Confirmed = supported by code/logs or a reproducible check. Reported = in the DC briefing but not reproduced. Hypothesis = plausible explanation that still needs evidence.

## Done

- **Briefing captured.** The DC raised name corruption/truncation, no post-submission correction path, stopped deemed approvals, pre-disbursement slowdown, suspected applicant-data leakage, and form usability barriers. The sales-call story remains a report, not proof of a leak.
- **OTP path checked locally.** A valid application request reached `/verify`, and the local fake gateway marked its message delivered. The user confirmed verification reached `/form/1`. This does not establish real-phone SMS delivery; this project points to the simulated gateway.
- **CAPTCHA guard added and verified.** `/apply` now compares the submitted value with the session answer before DB/SMS work. Wrong-answer baseline was HTTP 302; after the change, the wrong-answer and valid-answer tests passed. The normal image rebuild succeeded, and the tests pass without the Werkzeug shim. The local app container runs this image.
- **Document-upload contract corrected and verified.** The UI promises JPG/PDF up to 5 MB, while the original backend allowed only PDF up to 100 KB and exposed `ERR_VAL_47`. The backend now accepts signature-checked JPG/JPEG or PDF up to 5 MB, limits reads to 5 MB + 1 byte, and returns clear errors; the picker advertises the allowed extensions. Five upload tests passed, and the local app container was restarted with the new image.
- **Acknowledgment access restricted.** The original unauthenticated route returned HTTP 200 for an existing acknowledgment. It now allows an admin, the logged-in application owner, or the same session that just submitted the application. Four mocked authorization tests pass; the rebuilt app is active locally, and an anonymous request to the supplied route returned HTTP 403 without reading the PDF.
- **Application status ownership enforced.** The original route returned HTTP 200 to a different logged-in applicant. It now checks the application mobile against the session owner (admins remain authorized). The owner and non-owner tests pass; the app was rebuilt and restarted. An anonymous request redirects to status login.
- **Admin actions require admin sessions.** Citizen sessions previously passed the `logged_in` check on approve/reject. Both routes now require the separate `admin` flag. Citizen denial and admin access tests pass; the app image was rebuilt and the local app restarted.
- **Admin credentials removed from source/defaults.** Login now reads `SEWASETU_ADMIN_USERNAME` and `SEWASETU_ADMIN_PASSWORD`; it returns HTTP 503 when either is unset. Compose passes only those environment variables, `.env` is ignored, and `.env.example` contains blank values. The admin panel remains available when secrets are configured. A local secret is used for this workspace; public deployment secrets and the assessor handoff still need separate configuration.
- **Deployment secrets externalized.** The database password and Flask session key now come only from runtime environment variables; app.ini and Compose contain no secret defaults. Local `.env` is ignored; `.env.example` has blank placeholders. A value had been copied into `.env.example`, so the example was cleared and the local admin password rotated. Local login and portal liveness pass. No public deployment is connected.
- **Assamese applicant names preserved locally.** The old sanitizer cut UTF-8 names at 20 bytes; it now applies the 100-character database limit without cutting multibyte characters. Acknowledgment PDFs now embed Noto Sans Bengali with HarfBuzz shaping and a Latin fallback. Both regression tests failed against the old code; both pass after the fix, including a PDF Unicode-map check. The app image is rebuilt and active locally. No citizen record was changed.
- **Password-reset SQL injection removed locally.** The mobile lookups now use DB parameters. A SQL-shaped fictional mobile value failed the baseline test because it appeared inside SQL; it now remains a bound parameter and does not trigger the mocked reset path. The normal reset query/update path also remains parameterized. Both isolated tests pass; SMS was mocked.
- **Age and closing-time boundaries aligned with IST.** Eligibility now uses the Asia/Kolkata calendar date and the application window closes at the exclusive instant 2026-11-01 00:00 IST. Both fixed-clock tests failed against old behavior and pass after the fix; neither test writes to the database.
- **Correction and withdrawal requests implemented locally.** Applicants can request corrections or withdrawal for their own pending applications; staff review requests, and the original record is retained. Admin review is restricted to admin sessions and rechecks pending status while locking the request and application. Five regression tests cover owner access, non-owner denial, correction, withdrawal, and admin queue access. The selected one-person rule remains mobile-only because no approved citizen identifier was supplied; this does not prove one application per person.
- **Peak submission queries indexed locally.** Aggregated access and app logs tie 13,759 `/declaration` 500/504 responses to the same number of PostgreSQL “too many clients” errors, concentrated on month-end days 28-30. A read-only plan showed a sequential scan for mobile duplicate checks. Added concurrent indexes for `applications.mobile` and pending `submitted_at`; both post-change plans use indexes. This is a targeted improvement, not yet proof that peak-time connection exhaustion is resolved. No citizen rows were changed.
- **Deemed-approval failure confirmed.** The scheduler opens `config/settings.ini`; that file is absent, while `config/app.ini` exists and specifies a 15-day SLA. The daily cron log has timestamped successes through 14 Mar 2026, followed by repeated tracebacks for the missing file through the archive end on 30 Jun. The first failed run being 15 Mar is inferred from the daily 02:00 schedule and log order.
- **Scheduler config fix and regression tests are built and verified.** The job now reads `config/app.ini`. The baseline test failed on `FileNotFoundError`; both config-loading and mocked `main()` tests pass after the change. They used a fictional row with mocked PostgreSQL/SMS; no scheduler update ran against the live database. The scheduler image is rebuilt, but the running scheduler container has not been restarted with it.

## Prioritized backlog

| Rank | Card | Status and evidence | Next action / acceptance |
|---|---|---|---|
| 1 | Restore RTPS deemed approvals | **Workspace fix implemented and two isolated tests pass; rollout pending.** Historical cron failures follow the last success on 14 Mar. | Rebuild the image when Docker Hub is reachable, then verify the scheduled job in a controlled test environment. Confirm citizen-visible status and notifications before any production rollout. Never run an unreviewed bulk update against seeded records. |
| 2 | Close remaining authorization and personal-data exposure paths | **Acknowledgment, status ownership, admin-action checks, and reset SQL parameterization fixed locally.** The sales-call report remains unverified. See `app/app.py`. | Review remaining access and data paths; do not claim the rumor is confirmed without evidence. |
| 3 | Preserve Assamese names in records and acknowledgments | **Fixed locally.** Name sanitization counts characters up to the database limit; acknowledgment PDFs embed Noto Sans Bengali with shaping. Two isolated regression tests pass. | Verify PDF appearance in an actual browser/PDF viewer and retain Assamese probe coverage through deployment. |
| 4 | Add a safe correction/withdrawal path and enforce one application per person | **Staff-reviewed correction/withdrawal is implemented locally and covered by five regression tests; original application rows are retained.** User selected mobile-only duplicate checks. This is weaker than verified person-level uniqueness. | Verify the workflow in the local UI with fictional applications. Keep mobile-only behavior documented until an approved person identifier is available; do not claim person-level uniqueness. |
| 5 | Reproduce and reduce pre-disbursement slowdown | **Month-end correlation and slow duplicate-query path confirmed; supporting indexes applied locally.** Log counts match 13,759 database connection failures to 13,759 `/declaration` 500/504s. | Run synthetic concurrent traffic against a disposable database and measure latency/connection saturation. Do not infer the full connection-capacity cause from indexes alone. |

## Additional investigation cards

- **Form usability — reported, partly investigated.** The upload constraint mismatch is fixed locally. Walk through the remaining steps as an eligible fictional applicant; capture other instruction, validation, navigation, or recovery failures before changing them.
- **Deadline/timezone fixed locally.** Eligibility uses the IST date; the cutoff is 2026-11-01 00:00 IST exclusive. Fixed-clock regressions cover the 60th birthday and a request after midnight.
- **Rumored data leakage — incident unverified.** Review authorization paths and sanitized access logs for evidence. The code risks above justify fixes, but they do not establish that applicant data caused sales calls.

## Release gate

- [x] Briefing, code, schema, and historical logs reviewed; known reports are separated from unverified allegations.
- [x] Run all current focused app tests (latest recorded run: 39 passed, including change-request, runtime-secret, admin-secret, Assamese-name/PDF, reset-SQL, IST boundary, index, CAPTCHA, scheduler, upload, and authorization coverage).
- [ ] Select and finalize the top five fixes in citizen-impact order.
- [ ] Create one commit per selected fix in that order, each with a recorded failing baseline and passing regression test.
- [ ] Establish the correct project Git repository first: current `git rev-parse --show-toplevel` is `D:/Project`, this Sewa Setu directory has no `.git`, and its files appear untracked. Do not commit them into the parent workspace.
- [ ] Verify existing citizen records remain intact; tests so far use mocks/fictional data, but no before/after production-data audit has been done.
- [ ] Validate deemed-approval impact without applying a bulk update to seeded records; the scheduler image is built but its running container has not been restarted.
- [ ] Deploy to a VM/VPS, verify the public URL, keep it available through assessment, and confirm the deployed code matches the repository.
- [ ] Prepare assessor credentials, a private repository with full history and collaborator access, a repo zip including `.git`, and the short Loom video.
- [x] Move admin credentials out of source and Compose defaults into environment variables; fail closed if unset.
- [ ] Set unique secrets in the public deployment environment, verify admin login and panel on the deployed URL, then provide those credentials only through the assessor handoff.

## Sources

- The briefing audio is [dc-briefing.mp3](dc-briefing.mp3); its transcript was supplied in chat. See the [project brief](BRIEF.md) for assessment and handover requirements.
- [Investigation notes](investigation-notes.md)
- [Application routes and validation](app/app.py)
- [Deemed-approval job](app/scripts/deemed_approval.py) and [cron schedule](app/deploy/crontab)
- [Database schema](app/schema.sql)
- [Historical logs](logs/sewasetu-logs-jan-jun-2026.tar.gz)
