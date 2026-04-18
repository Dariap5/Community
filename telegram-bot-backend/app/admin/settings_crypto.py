from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SettingsCrypto:
    @staticmethod
    def _build_fernet() -> Fernet | None:
        settings = get_settings()
        if not settings.settings_crypto_key:
            return None
        return Fernet(settings.settings_crypto_key.encode("utf-8"))

    @staticmethod
    def encrypt(text: str) -> str:
        fernet = SettingsCrypto._build_fernet()
        if fernet is None:
            return text
        token = fernet.encrypt(text.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    @staticmethod
    def decrypt(text: str) -> str:
        fernet = SettingsCrypto._build_fernet()
        if not text.startswith("enc:") or fernet is None:
            return text
        raw = text[4:]
        try:
            return fernet.decrypt(raw.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return ""
