import hashlib
import hmac

from fastapi import HTTPException, Request, status

from app.config import get_settings

SESSION_KEY = "admin_authenticated"


def verify_password(raw_password: str) -> bool:
    settings = get_settings()
    if not settings.admin_password_hash:
        return False
    digest = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, settings.admin_password_hash)


def require_admin(request: Request) -> None:
    if request.session.get(SESSION_KEY) is True:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
