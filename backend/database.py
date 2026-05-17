import os
from contextlib import asynccontextmanager

import aiosqlite

from .config import settings


@asynccontextmanager
async def get_db():
    db_path = settings.db_path
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db() -> None:
    db_path = settings.db_path
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                username_hmac TEXT UNIQUE NOT NULL,
                username_enc TEXT NOT NULL,
                email_enc TEXT,
                passphrase_hash TEXT NOT NULL,
                recovery_token_hash TEXT,
                recovery_token_expires TEXT,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS account_sessions (
                token_hash TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title_enc TEXT NOT NULL,
                description_enc TEXT,
                timezone TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                day_start_hour INTEGER NOT NULL,
                day_end_hour INTEGER NOT NULL,
                admin_token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
                name_hmac TEXT NOT NULL,
                edit_token_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(event_id, name_hmac)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS availability (
                submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
                avail_date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('yes','maybe','no')),
                PRIMARY KEY (submission_id, avail_date, hour)
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sub_event ON submissions(event_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_avail_sub ON availability(submission_id)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_acct ON account_sessions(account_id)
        """)

        await db.commit()
