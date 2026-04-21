from cryptography.fernet import Fernet
from app.config import settings

_fernet = Fernet(settings.settings_crypto_key.encode())

def encrypt(value: str) -> str:
    return "enc:" + _fernet.encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    if not value.startswith("enc:"):
        return value
    return _fernet.decrypt(value[4:].encode()).decode()
