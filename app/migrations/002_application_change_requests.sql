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
