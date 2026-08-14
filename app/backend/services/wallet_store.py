"""Encrypted SQLite-backed wallet store."""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from backend.models.wallet import Wallet, WalletCreate, WalletUpdate

_FIXED_SALT = b"tradingagents-wallet-v1"
_SALT_LEN = 16


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from a user master password and per-wallet salt."""
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations=100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(raw)


def _make_salt() -> bytes:
    """Generate a new random salt for wallet encryption."""
    return os.urandom(_SALT_LEN)


def _encode_salt(salt: bytes) -> str:
    return base64.b64encode(salt).decode("ascii")


def _decode_salt(salt_b64: str | None) -> bytes:
    """Decode a stored salt; fall back to the legacy fixed salt if absent or invalid."""
    if not salt_b64:
        return _FIXED_SALT
    try:
        return base64.b64decode(salt_b64.encode("ascii"))
    except Exception:
        return _FIXED_SALT


def encrypt_key(plaintext: str, password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Encrypt a private key with the user's master password.

    Returns (encrypted_key, base64_salt). If no salt is provided, a new
    random salt is generated.
    """
    if salt is None:
        salt = _make_salt()
    token = Fernet(_derive_key(password, salt)).encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return token, _encode_salt(salt)


def decrypt_key(token: str, password: str, salt_b64: str | None = None) -> str | None:
    """Decrypt a private key. Returns None if the password is wrong or the salt is invalid."""
    try:
        salt = _decode_salt(salt_b64)
        return Fernet(_derive_key(password, salt)).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "wallets.db")


def _get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wallets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            chain TEXT NOT NULL,
            encrypted_key TEXT NOT NULL,
            salt TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Migrate existing tables that were created before the salt column existed.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(wallets)")}
    if "salt" not in columns:
        conn.execute("ALTER TABLE wallets ADD COLUMN salt TEXT")
    conn.commit()


class WalletStore:
    """Singleton SQLite-backed wallet store with encrypted keys."""

    _instance: WalletStore | None = None

    def __new__(cls) -> WalletStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            conn = _get_connection()
            _init_table(conn)
            conn.close()
        return cls._instance

    @staticmethod
    def _row_to_wallet(row: sqlite3.Row) -> Wallet:
        keys = row.keys()
        return Wallet(
            id=row["id"],
            name=row["name"],
            address=row["address"],
            chain=row["chain"],
            isDefault=bool(row["is_default"]),
            encryptedKey=row["encrypted_key"],
            salt=row["salt"] if "salt" in keys else None,
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
        )

    def list_wallets(self) -> list[Wallet]:
        conn = _get_connection()
        rows = conn.execute("SELECT * FROM wallets ORDER BY is_default DESC, name ASC").fetchall()
        conn.close()
        return [self._row_to_wallet(r) for r in rows]

    def get_wallet(self, wallet_id: str) -> Wallet | None:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_wallet(row)

    def get_default_wallet(self) -> Wallet | None:
        conn = _get_connection()
        row = conn.execute("SELECT * FROM wallets WHERE is_default = 1 LIMIT 1").fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_wallet(row)

    def create_wallet(self, payload: WalletCreate) -> Wallet:
        wallet_id = f"wallet-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        encrypted_key, salt_b64 = encrypt_key(payload.privateKey, payload.masterPassword)

        conn = _get_connection()
        if payload.isDefault:
            conn.execute("UPDATE wallets SET is_default = 0")

        conn.execute(
            """
            INSERT INTO wallets (id, name, address, chain, encrypted_key, salt, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                wallet_id,
                payload.name,
                payload.address,
                payload.chain,
                encrypted_key,
                salt_b64,
                int(payload.isDefault),
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return Wallet(
            id=wallet_id,
            name=payload.name,
            address=payload.address,
            chain=payload.chain,
            isDefault=payload.isDefault,
            encryptedKey=encrypted_key,
            salt=salt_b64,
            createdAt=now,
            updatedAt=now,
        )

    def update_wallet(self, wallet_id: str, payload: WalletUpdate) -> Wallet | None:
        existing = self.get_wallet(wallet_id)
        if not existing:
            return None

        conn = _get_connection()
        if payload.isDefault:
            conn.execute("UPDATE wallets SET is_default = 0")

        name = payload.name if payload.name is not None else existing.name
        is_default = payload.isDefault if payload.isDefault is not None else existing.isDefault
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            UPDATE wallets
            SET name = ?, is_default = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, int(is_default), now, wallet_id),
        )
        conn.commit()
        conn.close()
        return self.get_wallet(wallet_id)

    def delete_wallet(self, wallet_id: str) -> bool:
        conn = _get_connection()
        cursor = conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def decrypt_private_key(self, wallet_id: str, password: str) -> str | None:
        wallet = self.get_wallet(wallet_id)
        if not wallet:
            return None
        return decrypt_key(wallet.encryptedKey, password, wallet.salt)


def wallet_store() -> WalletStore:
    return WalletStore()
