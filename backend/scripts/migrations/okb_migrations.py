"""Controlled, idempotent schema migrations for the Occupational Knowledge Base.

Migration files are plain SQL, applied in lexical filename order. Every
statement is written to be safe to re-run, so the importer can apply the full
migration set on every reproducible rebuild without a separate migration
ledger.

The importer calls :func:`apply_okb_migrations` inside the same transaction as
the data load. PostgreSQL DDL is transactional, so a failed import rolls the
schema change back together with the data.
"""
from pathlib import Path

from sqlalchemy import text

MIGRATIONS_DIR = Path(__file__).resolve().parent


def iter_migration_files():
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def apply_okb_migrations(conn) -> list[str]:
    """Apply every SQL migration in order. Returns the applied filenames."""
    applied: list[str] = []
    for path in iter_migration_files():
        for statement in _statements(path.read_text(encoding="utf-8")):
            conn.execute(text(statement))
        applied.append(path.name)
    return applied
