"""JWT：家长身份 token / child-scoped token（规格 v2 §4.1 鉴权边界）。"""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.core.runtime_config import get_runtime_setting


def create_parent_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": "parent",
        "iat": now,
        "exp": now + timedelta(
            minutes=get_runtime_setting(
                "access_token_expire_minutes", settings.access_token_expire_minutes
            )
        ),
    }
    return jwt.encode(payload, settings.security_secret_key, algorithm="HS256")


def create_child_token(user_id: str, child_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": "child",
        "child_id": child_id,
        "iat": now,
        "exp": now + timedelta(
            minutes=get_runtime_setting(
                "child_token_expire_minutes", settings.child_token_expire_minutes
            )
        ),
    }
    return jwt.encode(payload, settings.security_secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.security_secret_key, algorithms=["HS256"])
