"""
Encrypted storage for data-provider API credentials (TrueData, DhanHQ, etc).
Same Fernet-based scheme as xillion/auth/credstore.py, kept in a parallel
table (data_provider_credential) since a provider credential is a distinct
concept from a broker credential even though the shape matches.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.auth.credstore import decrypt_payload, encrypt_payload
from xillion.db.models import DataProviderCredential


async def save_provider_credentials(
    db: AsyncSession, name: str, provider_name: str, payload: dict
) -> None:
    encrypted = encrypt_payload(payload)
    now = datetime.now(UTC).isoformat()
    existing = await db.get(DataProviderCredential, name)
    if existing:
        existing.encrypted_payload = encrypted
        existing.provider_name = provider_name
        existing.updated_at = now
    else:
        db.add(
            DataProviderCredential(
                name=name,
                provider_name=provider_name,
                encrypted_payload=encrypted,
                updated_at=now,
            )
        )
    await db.commit()


async def load_provider_credentials(db: AsyncSession, name: str) -> dict | None:
    row = await db.get(DataProviderCredential, name)
    if not row:
        return None
    try:
        return decrypt_payload(row.encrypted_payload)
    except Exception:
        return None


async def list_provider_credential_names(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(DataProviderCredential))
    return [
        {"name": r.name, "provider_name": r.provider_name, "updated_at": r.updated_at}
        for r in result.scalars().all()
    ]
