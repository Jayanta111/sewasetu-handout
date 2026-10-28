-- Sewa Setu Old Age Pension Portal - schema
-- NOTE: seed.sql (shipped separately) loads after this and contains the
-- production data. Do not re-run against a live database.

CREATE TABLE IF NOT EXISTS applications (
    id              SERIAL PRIMARY KEY,
    application_no  VARCHAR(20),
    applicant_name  VARCHAR(100),
    mobile          VARCHAR(15),
    dob             DATE,
    gender          VARCHAR(10),
    marital_status  VARCHAR(20),
    husband_name    VARCHAR(100),
    husband_employer VARCHAR(100),
    village         VARCHAR(100),
    block           VARCHAR(50),
    bank_account    VARCHAR(30),
    ifsc            VARCHAR(15),
    doc_path        VARCHAR(200),
    status          VARCHAR(20) DEFAULT 'PENDING',
    submitted_at    TIMESTAMP,
    decided_at      TIMESTAMP,
    decided_by      VARCHAR(50)
);

-- Status portal accounts (created at submission time)
CREATE TABLE IF NOT EXISTS portal_users (
    mobile        VARCHAR(15) PRIMARY KEY,
    password_hash VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS otps (
    id         SERIAL PRIMARY KEY,
    mobile     VARCHAR(15),
    code       VARCHAR(6),
    created_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS applications_mobile_idx
    ON applications (mobile);

CREATE INDEX IF NOT EXISTS applications_pending_submitted_idx
    ON applications (submitted_at)
    WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS application_change_requests (
    id              SERIAL PRIMARY KEY,
    application_id  INTEGER NOT NULL REFERENCES applications(id),
    requester_mobile VARCHAR(15) NOT NULL,
    request_type    VARCHAR(20) NOT NULL
                    CHECK (request_type IN ('CORRECTION', 'WITHDRAWAL')),
    field_name      VARCHAR(30),
    proposed_value  TEXT,
    details         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'APPROVED', 'DECLINED')),
    review_notes    TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     TIMESTAMP,
    reviewed_by     VARCHAR(100),
    CHECK (
        (request_type = 'CORRECTION'
         AND field_name IN ('applicant_name', 'dob', 'village', 'block',
                            'bank_account', 'ifsc')
         AND proposed_value IS NOT NULL)
        OR (request_type = 'WITHDRAWAL' AND field_name IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS application_change_requests_status_created_idx
    ON application_change_requests (status, created_at);
