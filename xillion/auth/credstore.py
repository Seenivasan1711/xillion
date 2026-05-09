"""
Encrypted storage for broker credentials.

Uses a Fernet key from the ENCRYPTION_KEY env var. If unset, auto-generates
one and persists to data/.encryption_key on first use (dev convenience).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.db.models import BrokerCredential


_KEY_FILE = Path("data/.encryption_key")


def _get_or_create_key() -> bytes:
    from xillion.config import get_settings

    raw = get_settings().encryption_key.strip()
    if raw:
        return raw.encode()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()
    _KEY_FILE.write_bytes(new_key)
    return new_key


def _fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def encrypt_payload(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_payload(blob: str) -> dict:
    return json.loads(_fernet().decrypt(blob.encode()).decode())


async def save_credentials(
    db: AsyncSession, name: str, broker_name: str, payload: dict
) -> None:
    encrypted = encrypt_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    existing = await db.get(BrokerCredential, name)
    if existing:
        existing.encrypted_payload = encrypted
        existing.broker_name = broker_name
        existing.updated_at = now
    else:
        db.add(
            BrokerCredential(
                name=name,
                broker_name=broker_name,
                encrypted_payload=encrypted,
                updated_at=now,
            )
        )
    await db.commit()


async def load_credentials(db: AsyncSession, name: str) -> Optional[dict]:
    row = await db.get(BrokerCredential, name)
    if not row:
        return None
    try:
        return decrypt_payload(row.encrypted_payload)
    except Exception:
        return None


async def list_credential_names(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(BrokerCredential))
    return [
        {"name": r.name, "broker_name": r.broker_name, "updated_at": r.updated_at}
        for r in result.scalars().all()
    ]
