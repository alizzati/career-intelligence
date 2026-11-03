BEGIN;

CREATE SCHEMA IF NOT EXISTS okb AUTHORIZATION postgres;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION postgres;

-- No database extensions are required for the OKB target schema.
-- Operational imports remain in the okb/app split; the public schema is left untouched.

COMMIT;
