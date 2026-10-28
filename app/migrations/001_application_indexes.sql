-- Apply each statement with autocommit (for example: psql -f this_file.sql).
-- CONCURRENTLY avoids blocking application writes while these indexes are built.
CREATE INDEX CONCURRENTLY IF NOT EXISTS applications_mobile_idx
    ON applications (mobile);

CREATE INDEX CONCURRENTLY IF NOT EXISTS applications_pending_submitted_idx
    ON applications (submitted_at)
    WHERE status = 'PENDING';
