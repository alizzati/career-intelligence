"""
Database engine/session management.

Single source of truth for the DB connection. Repositories import `engine`
from here; nothing outside app/core/ and app/repositories/ should hold a
raw connection.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = os.environ.get(
    "CAREER_DB_URL",
    "postgresql+psycopg2://postgres:MySQL0512@localhost:5433/career_intelligence",
)

# pool_pre_ping avoids stale-connection errors after periods of idleness
# (relevant here since the container's postgres service can restart between sessions)
engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)