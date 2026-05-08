import pyotp


def generate_secret() -> str:
    return pyotp.random_base32()


def get_provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Xillion")


def verify_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def _fernet():
    from xillion.config import get_settings
    key = get_settings().encryption_key.strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def encrypt_secret(secret: str) -> str:
    f = _fernet()
    if f is None:
        return secret
    return f.encrypt(secret.encode()).decode()


def decrypt_secret(stored: str) -> str:
    f = _fernet()
    if f is None:
        return stored
    return f.decrypt(stored.encode()).decode()
