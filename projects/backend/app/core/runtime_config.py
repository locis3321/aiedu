"""运行时配置：后台 system_settings 优先，环境变量回退。

- 普通参数：DB value_json 直接存原始值；
- 凭据：DB 存 {"enc": Fernet密文}，读取时解密（SECURITY_SECRET_KEY 变更显式失败）；
- 未在后台配置时回退环境变量（get_settings()），保证部署默认可用。
"""

from typing import Any

from app.core.crypto import decrypt_secret
from app.core.errors import ApiError


def _get_row(key: str) -> dict | None:
    from app.admin_api.models import SystemSetting
    from app.storage.db import create_session_factory

    factory = create_session_factory()
    try:
        with factory() as session:
            row = session.get(SystemSetting, key)
            return row.value_json if row is not None else None
    except Exception:
        # DB 不可达（如单元测试无真实库）：回退环境变量默认，不阻断服务
        return None


def get_runtime_setting(key: str, default: Any) -> Any:
    """后台配置优先；无记录返回 default（通常来自 env Settings）。"""
    value = _get_row(key)
    if value is None or "enc" in value:
        return default
    return value.get("value", default)


def get_runtime_secret(key: str, default: str | None) -> str | None:
    """后台加密凭据优先；解密失败显式报错；无记录回退 default。"""
    value = _get_row(key)
    if value is None or "enc" not in value:
        return default
    try:
        return decrypt_secret(value["enc"])
    except ApiError:
        raise
    except Exception as e:  # 防御：非预期解密错误同样显式失败
        raise ApiError(
            500, "SECRET_DECRYPT_FAILED", f"凭据解密失败：{key}"
        ) from e
