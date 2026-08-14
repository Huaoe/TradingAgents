"""Tests for wallet encryption and storage."""

from __future__ import annotations

from backend.models.wallet import WalletCreate
from backend.services.wallet_store import (
    _FIXED_SALT,
    WalletStore,
    decrypt_key,
    encrypt_key,
)


def test_encrypt_decrypt_round_trip():
    plaintext = "0xdeadbeef"
    password = "super-secret-password"
    token, salt_b64 = encrypt_key(plaintext, password)

    assert decrypt_key(token, password, salt_b64) == plaintext
    assert decrypt_key(token, "wrong-password", salt_b64) is None


def test_per_wallet_salt_is_unique():
    password = "super-secret-password"
    plaintext = "0xdeadbeef"

    token1, salt1 = encrypt_key(plaintext, password)
    token2, salt2 = encrypt_key(plaintext, password)

    assert salt1 != salt2
    assert token1 != token2
    assert decrypt_key(token1, password, salt1) == plaintext
    assert decrypt_key(token2, password, salt2) == plaintext


def test_wallet_store_create_and_fetch():
    store = WalletStore()
    payload = WalletCreate(
        name="test-wallet",
        address="0x" + "a" * 40,
        chain="hyperliquid",
        isDefault=False,
        privateKey="0xdeadbeef",
        masterPassword="master-password",
    )

    wallet = store.create_wallet(payload)
    assert wallet.id is not None
    assert wallet.salt is not None

    fetched = store.get_wallet(wallet.id)
    assert fetched is not None
    assert fetched.address == payload.address

    decrypted = store.decrypt_private_key(wallet.id, payload.masterPassword)
    assert decrypted == payload.privateKey
    assert store.decrypt_private_key(wallet.id, "wrong-password") is None

    wallets = store.list_wallets()
    assert any(w.id == wallet.id for w in wallets)


def test_legacy_fixed_salt_migration():
    store = WalletStore()
    password = "master-password"
    plaintext = "0xlegacy-key"
    token, _ = encrypt_key(plaintext, password, salt=_FIXED_SALT)

    from backend.services.wallet_store import _get_connection

    conn = _get_connection()
    wallet_id = "wallet-legacy01"
    conn.execute(
        """
        INSERT INTO wallets (id, name, address, chain, encrypted_key, salt, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (wallet_id, "legacy", "0x" + "b" * 40, "hyperliquid", token, None, 0, "2024-01-01", "2024-01-01"),
    )
    conn.commit()
    conn.close()

    assert store.decrypt_private_key(wallet_id, password) == plaintext
