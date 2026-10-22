from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from server import config


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        parts = str(stored_hash or "").split("$")
        if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
            iterations = int(parts[1])
            salt = parts[2]
            digest = parts[3]
        elif len(parts) == 3 and parts[0] == "pbkdf2_sha256":
            iterations = 100_000
            salt = parts[1]
            digest = parts[2]
        else:
            return False
    except (TypeError, ValueError):
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256", str(password).encode("utf-8"), salt.encode("utf-8"), iterations
    )
    return hmac.compare_digest(check.hex(), digest)


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=config.SESSION_DAYS)
    conn.execute(
        "DELETE FROM sessions WHERE expires_at <= ?",
        (now.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (
            token,
            user_id,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            expires.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    return token


def delete_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def session_user(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.username, u.role, u.created_at, s.expires_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at > ?
        """,
        (token, _now()),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


def find_user(conn: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, username, password_hash, role, created_at FROM users WHERE username = ? COLLATE NOCASE",
        (str(username or "").strip(),),
    ).fetchone()
    return dict(row) if row is not None else None
