-- Migration: dbops_phase3_4_user_role_lowercase.sql
-- I-4: UserRole strict typing. Lowercase all existing role values in
-- dbops.users and TRIM whitespace so the strict get_current_admin
-- comparison (current_user.role == "admin") does not reject historical
-- data with mixed case or trailing whitespace.
--
-- Idempotent: re-running is a no-op because all values are already
-- lowercased + trimmed by the first run.
--
-- Pre-flight (read-only):
--   SELECT role, count(*) FROM dbops.users GROUP BY role ORDER BY role;

BEGIN;

-- 1) Lowercase any historical mixed-case values. UPDATE returns 0 rows
--    when no match exists, so this is safe to re-run.
UPDATE dbops.users
SET role = LOWER(role)
WHERE role <> LOWER(role);

-- 2) Strip leading/trailing whitespace. Same idempotency guarantee.
UPDATE dbops.users
SET role = TRIM(role)
WHERE role <> TRIM(role);

-- 3) Replace any NULL / empty / unknown values with the safe default
--    'user'. Only acts on rows that would otherwise fail the strict
--    role check; admins keep their role.
UPDATE dbops.users
SET role = 'user',
    updated_at = NOW()
WHERE role IS NULL
   OR role = ''
   OR LOWER(role) NOT IN ('admin', 'dba', 'user');

-- 4) Optional CHECK constraint to lock the canonical spellings at the
--    DB layer. Skipped by default (out of scope for I-4) — see plan.
-- ALTER TABLE dbops.users
--   ADD CONSTRAINT chk_users_role
--   CHECK (role IN ('admin', 'dba', 'user'));

COMMIT;

-- Post-check (read-only):
--   SELECT DISTINCT role FROM dbops.users ORDER BY role;
-- Expected: 'admin', 'dba', 'user' (no mixed case, no whitespace, no NULL).
