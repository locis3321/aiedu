"""密钥加密工具：Fernet 对称加密。

- 密钥材料优先 CREDENTIAL_ENCRYPTION_KEY，未配置时回退 SECURITY_SECRET_KEY（向后兼容）；
- 密文入库、永不返回明文、不进日志；
- 密钥变更会导致既有密文无法解密 → 显式抛错（不静默回退）。
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import ApiError


def _fernet() -> Fernet:
    settings = get_settings()
    material = settings.credential_encryption_key or settings.security_secret_key
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    """加密明文，返回可入库的 token。"""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """解密密文；SECURITY_SECRET_KEY 不匹配时显式失败。"""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ApiError(
            500,
            "SECRET_DECRYPT_FAILED",
            "凭据解密失败：SECURITY_SECRET_KEY 可能已变更，请重新配置密钥",
        ) from e
