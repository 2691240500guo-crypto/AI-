"""Application-level AES-256-GCM protection for user health text."""
import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings

_AAD = b"healthybot-health-v1"
_PREFIX = "enc:v1:"
_BLOB_PREFIX = b"encimg:v1:"


def encryption_configured() -> bool:
    """Whether deployment supplied a dedicated health-data key."""
    return bool(settings.HEALTH_DATA_ENCRYPTION_KEY.strip())


def _key() -> bytes:
    # A stable development fallback keeps existing local demos readable. Production must set
    # HEALTH_DATA_ENCRYPTION_KEY through the deployment secret manager.
    raw = settings.HEALTH_DATA_ENCRYPTION_KEY or settings.JWT_SECRET
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_text(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        value = str(value)
    if value.startswith(_PREFIX):
        return value
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode("utf-8"), _AAD)
    token = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{_PREFIX}{token}"


def decrypt_text(value: str | None) -> str | None:
    if value is None or value == "" or not isinstance(value, str) or not value.startswith(_PREFIX):
        # Existing rows from before protection remain readable during migration.
        return value
    try:
        raw = base64.urlsafe_b64decode(value[len(_PREFIX):].encode("ascii"))
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], _AAD).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("无法解密健康数据，请检查 HEALTH_DATA_ENCRYPTION_KEY") from exc


def decrypt_chain(value: str | None) -> str | None:
    """逐层还原健康数据明文。

    历史数据里出现过两类"套娃"写法，都会导致用户读到密文串：
      1. 重复加密：外层解出来仍是 enc:v1: 密文
      2. 被 JSON 引号包裹：外层解出来是 "enc:v1:..." （含引号）
    这里循环剥离最多 6 层；任何一步失败都原样返回，避免因密钥问题影响业务。
    """
    for _ in range(6):
        if not isinstance(value, str):
            return value
        changed = False
        if value.startswith(_PREFIX):
            try:
                nxt = decrypt_text(value)
            except Exception:  # noqa: BLE001
                return value
            if nxt is not None and nxt != value:
                value = nxt
                changed = True
        elif len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            try:
                nxt = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                nxt = None
            if isinstance(nxt, str) and nxt != value:
                value = nxt
                changed = True
        if not changed:
            return value
    return value


def encrypt_bytes(value: bytes | None) -> bytes | None:
    """Encrypt binary health assets before they enter object storage."""
    if value is None or value.startswith(_BLOB_PREFIX):
        return value
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value, _AAD + b"-blob")
    return _BLOB_PREFIX + nonce + ciphertext


def decrypt_bytes(value: bytes | None) -> bytes | None:
    if value is None or not value.startswith(_BLOB_PREFIX):
        return value
    raw = value[len(_BLOB_PREFIX):]
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], _AAD + b"-blob")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("无法解密健康图片，请检查 HEALTH_DATA_ENCRYPTION_KEY") from exc


class EncryptedText(TypeDecorator):
    """Transparent AES-256-GCM storage for free-form health text."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_text(value)

    def process_result_value(self, value, dialect):
        return decrypt_chain(value)


class EncryptedJSON(TypeDecorator):
    """JSON-compatible values stored as authenticated ciphertext in a text column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str) and value.startswith(_PREFIX):
            return value
        return encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def process_result_value(self, value, dialect):
        raw = decrypt_chain(value)
        if raw is None or raw == "":
            return raw
        if not isinstance(raw, str):
            return raw
        # 明文本身是 JSON 文本（数组/对象）时解析回结构体
        text = raw.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                return json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return raw
        return raw
