import hashlib
import hmac
import json


class PaymentSignatureVerifier:
    @staticmethod
    def verify(secret: str, payload: dict, signature: str) -> bool:
        message = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, signature)
