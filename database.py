from __future__ import annotations

import aiosqlite
import logging
from config import DB_PATH
from crypto import encrypt, decrypt

logger = logging.getLogger(__name__)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS servers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    host        TEXT NOT NULL,
    ssh_port    INTEGER NOT NULL DEFAULT 22,
    username    TEXT NOT NULL DEFAULT 'root',
    auth_type   TEXT NOT NULL DEFAULT 'password',  -- 'password' | 'key'
    credential  TEXT NOT NULL DEFAULT '',           -- encrypted password or key
    proxy_port  INTEGER DEFAULT 443,
    domain      TEXT DEFAULT 'apple.com',
    dns         TEXT DEFAULT '1.1.1.1',
    tls_mode    TEXT DEFAULT 'fake',                -- 'fake' | 'real'
    real_domain TEXT DEFAULT '',                     -- domain for Real-TLS
    le_email    TEXT DEFAULT '',                     -- Let's Encrypt email
    secret      TEXT DEFAULT '',
    status      TEXT DEFAULT 'new',                 -- new | installed | error
    server_ip   TEXT DEFAULT '',
    tme_link    TEXT DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT DEFAULT '',
    first_name  TEXT DEFAULT '',
    is_admin    INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_MIGRATIONS = [
    ("tls_mode", "TEXT DEFAULT 'fake'"),
    ("real_domain", "TEXT DEFAULT ''"),
    ("le_email", "TEXT DEFAULT ''"),
]


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(CREATE_TABLES)
        await self._db.commit()
        await self._migrate()

    async def _migrate(self):
        for col, typedef in _MIGRATIONS:
            try:
                await self._db.execute(
                    f"ALTER TABLE servers ADD COLUMN {col} {typedef}"
                )
            except Exception:
                pass
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def upsert_user(self, user_id: int, username: str = "", first_name: str = "", is_admin: bool = False):
        await self._db.execute(
            """INSERT INTO users (user_id, username, first_name, is_admin)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=excluded.username,
                 first_name=excluded.first_name""",
            (user_id, username, first_name, int(is_admin)),
        )
        await self._db.commit()

    async def add_server(
        self,
        user_id: int,
        name: str,
        host: str,
        ssh_port: int,
        username: str,
        auth_type: str,
        credential: str,
        proxy_port: int = 443,
        domain: str = "apple.com",
        dns: str = "1.1.1.1",
        tls_mode: str = "fake",
        real_domain: str = "",
        le_email: str = "",
    ) -> int:
        encrypted_credential = encrypt(credential)
        cursor = await self._db.execute(
            """INSERT INTO servers
               (user_id, name, host, ssh_port, username, auth_type, credential,
                proxy_port, domain, dns, tls_mode, real_domain, le_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, name, host, ssh_port, username, auth_type, encrypted_credential,
             proxy_port, domain, dns, tls_mode, real_domain, le_email),
        )
        await self._db.commit()
        return cursor.lastrowid

    @staticmethod
    def _decrypt_row(row: dict) -> dict:
        if row.get("credential"):
            try:
                row["credential"] = decrypt(row["credential"])
            except Exception:
                pass
        return row

    async def get_servers(self, user_id: int) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM servers WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        )
        rows = await cursor.fetchall()
        return [self._decrypt_row(dict(r)) for r in rows]

    async def get_server(self, server_id: int, user_id: int) -> dict | None:
        cursor = await self._db.execute(
            "SELECT * FROM servers WHERE id = ? AND user_id = ?", (server_id, user_id)
        )
        row = await cursor.fetchone()
        return self._decrypt_row(dict(row)) if row else None

    async def update_server(self, server_id: int, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values())
        vals.append(server_id)
        await self._db.execute(
            f"UPDATE servers SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", vals
        )
        await self._db.commit()

    async def delete_server(self, server_id: int, user_id: int):
        await self._db.execute(
            "DELETE FROM servers WHERE id = ? AND user_id = ?", (server_id, user_id)
        )
        await self._db.commit()

    async def get_stats(self) -> dict:
        stats: dict = {}
        row = await (await self._db.execute("SELECT COUNT(*) FROM users")).fetchone()
        stats["users"] = row[0]
        row = await (await self._db.execute("SELECT COUNT(*) FROM servers")).fetchone()
        stats["servers"] = row[0]
        cursor = await self._db.execute(
            "SELECT status, COUNT(*) FROM servers GROUP BY status"
        )
        stats["by_status"] = {r[0]: r[1] for r in await cursor.fetchall()}
        row = await (await self._db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM servers"
        )).fetchone()
        stats["users_with_servers"] = row[0]
        return stats

    async def get_all_users(self) -> list[dict]:
        cursor = await self._db.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [dict(r) for r in await cursor.fetchall()]

    async def get_all_servers(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT s.*, u.username as tg_username FROM servers s "
            "LEFT JOIN users u ON s.user_id = u.user_id "
            "ORDER BY s.created_at DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]
