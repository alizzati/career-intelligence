# T5.1 — Safe Provisioning of Target PostgreSQL Database

**Status:** COMPLETE

**Date:** 2026-11-02
**Scope:** Database and schema provisioning only. No workbook import, no user-data migration, no application cutover.

---

## 1. Summary

A new PostgreSQL database `career_intelligence_okb` was created on the existing server with two schemas, `app` and `okb`, both owned by the existing `postgres` role. The database-level `search_path` for this database only was set to `app, okb` and verified from a fresh session. No tables or rows were created in either schema.

Both protected databases (`career_intelligence`, `career_intelligence_e2e_test`) were read in read-only transactions before and after provisioning. Their schemas, table lists, table counts, and exact row counts are identical before and after.

No workbook was imported, no user data was copied, and no application configuration was changed.

---

## 2. Connection and server identity

| Item | Value |
|---|---|
| Host | `localhost` |
| Port | `5433` |
| Server address reported by PostgreSQL | `::1/128` (loopback) |
| PostgreSQL version | `PostgreSQL 16.4, compiled by Visual C++ build 1941, 64-bit` |
| Connection mechanism | `psycopg2` using the values in `backend/.env` (`CAREER_DB_HOST`, `CAREER_DB_PORT`, `CAREER_DB_USER`, `CAREER_DB_PASSWORD`) |
| Database used for admin operations | `postgres` |
| Credentials | Not reproduced in this report |

The `CAREER_DB_URL` variable is unset in `backend/.env`; the application builds its URL from the component settings above. The connection target matches the configuration used by the running application (single `CAREER_DB_URL` / component settings in `backend/app/core/db.py`).

---

## 3. Preflight evidence

### 3.1 Databases before provisioning

`career_intelligence`, `career_intelligence_e2e_test`, `postgres`

### 3.2 Protected database baseline

Both protected databases contained only the `public` schema and **25 tables** each.

**`career_intelligence`** (25 tables):

| Table | Rows |
|---|---|
| `public.career_occupations` | 12 |
| `public.career_skills` | 155 |
| `public.careers` | 10 |
| `public.competency_skills` | 79 |
| `public.competency_units` | 146 |
| `public.etl_transform_log` | 157 |
| `public.occupation_competencies` | 10 |
| `public.occupation_source_mapping` | 26 |
| `public.occupations` | 8 |
| `public.provenance` | 23 |
| `public.skill_groups` | 17 |
| `public.skill_source_evidence` | 97 |
| `public.skills` | 87 |
| `public.skkni_standards` | 9 |
| `public.tasks` | 35 |
| `public.technologies` | 120 |
| `public.user_certifications` | 29 |
| `public.user_education` | 29 |
| `public.user_experience` | 60 |
| `public.user_preferences` | 0 |
| `public.user_profiles` | 6 |
| `public.user_projects` | 56 |
| `public.user_skill_evidence` | 94 |
| `public.user_skills` | 271 |
| `public.users` | 74 |

**`career_intelligence_e2e_test`** (25 tables): the same table list, with the OKB tables matching the counts above and all nine `user_*` tables empty (0 rows).

### 3.3 Target existence

`career_intelligence_okb` did **not** exist before provisioning (checked in `pg_database`).

### 3.4 Stop-condition review

| Stop condition | Result |
|---|---|
| Either protected database cannot be identified reliably | Not triggered — both found |
| Connection points to an unexpected host/port | Not triggered — `localhost:5433`, matches `backend/.env` |
| Target already exists with unexpected objects/data | Not triggered — target absent |
| Required permissions unavailable | Not triggered — role can create databases |
| Provisioning could affect a protected database | Not triggered — DDL confined to the new database |
| Design document has blocking inconsistencies | Not triggered for provisioning (see §4) |

---

## 4. Design-document verification (T4-R2C)

The controlling design document `docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md` was checked before provisioning:

| Required correction | Present? | Evidence |
|---|---|---|
| `CAREER_OCCUPATION.record_id` resolution based on actual workbook values | Yes | §6.1 allowlist row: 65 workbook rows, 12 distinct `career_id\|occupation_id` values, all match `^[A-Z0-9]+\|[A-Z0-9]+$`, all pairs exist |
| Independent target/source statuses | Yes | §6.1: target `RESOLVED / ORPHAN_TARGET / INVALID_TABLE / AMBIGUOUS`; source `RESOLVED / UNRESOLVED / QUARANTINED` |
| User-data migration optional and deferred | Yes | Revision note T4-R2B item 3; §10.2 Phase 3 is optional and not a prerequisite |
| No eligibility from `operational_evidence_present` | Yes | §7.1 and revision note T4-R2C |
| Dataset-level manual review approval (T4-R2C) | Yes | Revision note T4-R2C; §7.1–§7.2; `workbook_review_approval` |

**Noted deviation from the task text:** the task's §2 bullet "Zero VALIDATED records remain zero eligible records" reflects the pre-T4-R2C rule. The controlling T4-R2C revision explicitly replaced the per-record `VALIDATED` gate with a dataset-level manual-review approval. The design document is internally consistent; this stale bullet was **not** reintroduced. Eligibility is not evaluated or activated by this provisioning task in any case.

---

## 5. Provisioning performed

### 5.1 Database

```sql
CREATE DATABASE career_intelligence_okb
    WITH OWNER = postgres
         ENCODING = 'UTF8'
         LC_COLLATE = 'Indonesian_Indonesia.1252'
         LC_CTYPE = 'Indonesian_Indonesia.1252'
         TEMPLATE = template0;
```

Encoding and locale match the existing databases on the server (`UTF8`, `Indonesian_Indonesia.1252`).

### 5.2 Schemas

```sql
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION postgres;
CREATE SCHEMA IF NOT EXISTS okb AUTHORIZATION postgres;
```

Both schemas are owned by the existing `postgres` role. No tables were created. The default `public` schema remains present but was not used.

### 5.3 Search path

```sql
ALTER DATABASE career_intelligence_okb SET search_path TO app, okb;
```

This setting applies only when connecting to `career_intelligence_okb`. It does not change `search_path` for either protected database or the server default.

### 5.4 Role and permissions

- Existing role reused: `postgres` (the same role the application is configured to use).
- No new role was created.
- No new privileges were granted; schema ownership follows from `AUTHORIZATION postgres`.
- No global PostgreSQL configuration was changed.

**Warning:** the existing application role is already a superuser (`rolsuper = true`). This is a pre-existing condition of the local development setup, not something introduced by this task. No superuser grant was made. If least-privilege operation is required for the thesis environment, creating a dedicated non-superuser role is a separate, approval-gated decision.

---

## 6. Post-provisioning verification

### 6.1 Target database

| Check | Result |
|---|---|
| Database name is exactly `career_intelligence_okb` | PASS |
| Current database on connection | `career_intelligence_okb` |
| Schemas present | `app`, `okb` (plus default `public`) |
| Schema owners | `app` → `postgres`; `okb` → `postgres` |
| Tables created in `app`/`okb` | 0 |
| User tables in target | 0 |
| `search_path` on fresh session | `app, okb` |
| Resolves `app` before `okb` | PASS |
| Encoding / collation | `UTF8` / `Indonesian_Indonesia.1252` |
| Owner | `postgres` |

### 6.2 Protected-database before/after comparison

| Database | Schemas before/after | Table count before/after | Row counts before/after |
|---|---|---|---|
| `career_intelligence` | `public` / `public` | 25 / 25 | Identical (no diffs) |
| `career_intelligence_e2e_test` | `public` / `public` | 25 / 25 | Identical (no diffs) |

Comparison covered the full table list and exact `count(*)` for every table. Missing tables: none. Extra tables: none. Changed row counts: none.

### 6.3 Databases after provisioning

`career_intelligence`, `career_intelligence_e2e_test`, `career_intelligence_okb`, `postgres`

(The only global change is the addition of the new database, which is the intended deliverable.)

---

## 7. Commands and SQL checks used

All checks were executed with read-only transactions (`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` / `set_session(readonly=True)`). Credentials were read from `backend/.env` at runtime and were not written to any repository file or this report.

Representative checks:

```sql
-- databases
SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;

-- identity / version
SELECT version();
SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();

-- schemas
SELECT nspname FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
ORDER BY nspname;

-- tables
SELECT schemaname, relname FROM pg_stat_user_tables ORDER BY schemaname, relname;

-- exact row counts (per table)
SELECT count(*) FROM "<schema>"."<table>";
```

Provisioning DDL is listed in §5. Verification scripts were temporary files under `C:\Users\My Thinkpad\AppData\Local\Temp\opencode\` and were not added to the repository.

---

## 8. Warnings and deviations

1. **Stale eligibility bullet in the task brief.** The task's preflight list still says "Zero VALIDATED records remain zero eligible records". The controlling T4-R2C revision replaced that gate with dataset-level manual review approval. The document was not reverted; no blocking inconsistency affects provisioning.
2. **Existing application role is a superuser.** `postgres` is the configured application role and is a superuser. This is pre-existing and unchanged. No superuser privilege was granted by this task.
3. **Default `public` schema.** A newly created database includes `public` by default. It was left in place and is unused; no application tables exist in it.
4. **`search_path` is database-scoped.** It applies only to `career_intelligence_okb`; protected databases and global defaults are unchanged.
5. **No dedicated least-privilege role was created**, per the instruction to reuse existing roles and avoid unnecessary global changes.

---

## 9. Explicit confirmations

- No workbook (extended or legacy) was imported.
- No user data was copied or migrated from either protected database.
- No database migration was run.
- No application cutover occurred; `CAREER_DB_URL`, `.env`, and runtime configuration were not changed.
- No application was started against the new database.
- No table was created in `app` or `okb`.
- No object in either protected database was dropped, truncated, renamed, altered, or written.
- No global PostgreSQL configuration was changed.
- No LLM calls, CV extraction, browser automation, or formal experiments were run.

---

## 10. Files created or modified

| File | Change |
|---|---|
| `docs/audits/T5_1_DATABASE_PROVISIONING_REPORT.md` | Created (this report) |

No source code, workbook, database schema file, importer, or runtime configuration was modified.

---

## 11. Verification checklist

| Completion criterion | Result |
|---|---|
| `career_intelligence_okb` exists | PASS |
| `app` and `okb` schemas exist | PASS |
| Search path resolves `app` before `okb` | PASS |
| Schema ownership/permissions verified | PASS |
| Both protected databases pass before/after comparison | PASS |
| Provisioning report created with actual evidence | PASS |

**T5.1 status: COMPLETE.**
