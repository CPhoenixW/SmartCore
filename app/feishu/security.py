from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HEADER_TIMESTAMP = "x-lark-request-timestamp"
HEADER_NONCE = "x-lark-request-nonce"
HEADER_SIGNATURE = "x-lark-signature"

DEFAULT_REPLAY_MAX_AGE_SECONDS = 300


class FeishuSecurityError(Exception):
    """Raised when a Feishu callback fails security validation."""


def compute_signature(
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
) -> str:
    content = f"{timestamp}{nonce}{encrypt_key}{body}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_signature(
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
    signature: str,
) -> bool:
    expected = compute_signature(timestamp, nonce, encrypt_key, body)
    return hmac.compare_digest(expected, signature)


def verify_timestamp(
    timestamp: str,
    *,
    now: float | None = None,
    max_age_seconds: int = DEFAULT_REPLAY_MAX_AGE_SECONDS,
) -> bool:
    try:
        request_ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = now if now is not None else time.time()
    return abs(current - request_ts) <= max_age_seconds


def verify_token(token: str | None, expected: str) -> bool:
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


def decrypt_event_payload(encrypt_key: str, encrypted: str) -> dict[str, Any]:
    cipher_text = base64.b64decode(encrypted)
    if len(cipher_text) < 17:
        raise FeishuSecurityError("invalid encrypted payload")
    iv = cipher_text[:16]
    encrypted_bytes = cipher_text[16:]
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_bytes) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(decrypted) + unpadder.finalize()
    payload = json.loads(plain.decode("utf-8"))
    if not isinstance(payload, dict):
        raise FeishuSecurityError("decrypted payload must be a JSON object")
    return payload


def validate_request_headers(
    headers: dict[str, str],
    *,
    encrypt_key: str,
    body: str,
    now: float | None = None,
    max_age_seconds: int = DEFAULT_REPLAY_MAX_AGE_SECONDS,
) -> None:
    normalized = {key.lower(): value for key, value in headers.items()}
    timestamp = normalized.get(HEADER_TIMESTAMP)
    nonce = normalized.get(HEADER_NONCE)
    signature = normalized.get(HEADER_SIGNATURE)
    if not timestamp or not nonce or not signature:
        raise FeishuSecurityError("missing signature headers")
    if not verify_timestamp(timestamp, now=now, max_age_seconds=max_age_seconds):
        raise FeishuSecurityError("timestamp outside allowed window")
    if not verify_signature(timestamp, nonce, encrypt_key, body, signature):
        raise FeishuSecurityError("invalid signature")


def parse_event_payload(
    body: str,
    *,
    encrypt_key: str,
    verification_token: str,
) -> dict[str, Any]:
    outer = json.loads(body)
    if not isinstance(outer, dict):
        raise FeishuSecurityError("invalid request body")

    if "encrypt" in outer:
        payload = decrypt_event_payload(encrypt_key, outer["encrypt"])
    else:
        payload = outer

    if payload.get("type") == "url_verification":
        if not verify_token(payload.get("token"), verification_token):
            raise FeishuSecurityError("invalid verification token")
        return payload

    token = payload.get("token")
    if token is None and isinstance(payload.get("header"), dict):
        token = payload["header"].get("token")
    if not verify_token(token, verification_token):
        raise FeishuSecurityError("invalid verification token")
    return payload
