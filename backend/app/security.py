import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional, Tuple


def random_urlsafe(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def build_pkce_pair() -> Tuple[str, str]:
    verifier = random_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def sign_payload(payload: Dict[str, Any], secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).decode("utf-8").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).digest()
    signed = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"{encoded}.{signed}"


def verify_payload(token: str, secret: str, max_age_seconds: int = 60 * 60 * 24 * 7) -> Optional[Dict[str, Any]]:
    try:
        encoded, signed = token.split(".", 1)
        expected_sig = hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(_pad_base64(signed))
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(_pad_base64(encoded)).decode("utf-8"))
        issued_at = int(payload.get("iat", 0))
        if time.time() - issued_at > max_age_seconds:
            return None
        return payload
    except Exception:
        return None


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)
