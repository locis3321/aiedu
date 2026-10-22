"""SmsProvider 工厂：ak/sk 已配置 → 腾讯云；开发环境 → dev fallback；否则显式未接入。

护栏8：未接入渠道显式报错（503），不静默降级为"验证码已发送"的假成功；
dev fallback 仅限 app_env=development，生产无凭据时 503。
"""

from app.core.config import get_settings
from app.core.errors import ApiError
from app.sms.base import SmsProvider
from app.sms.dev import DevSmsProvider
from app.sms.tencent import TencentCloudSmsProvider


def get_sms_provider() -> SmsProvider:
    from app.core.runtime_config import get_runtime_secret

    settings = get_settings()
    secret_id = get_runtime_secret("sms_secret_id", settings.sms_secret_id)
    secret_key = get_runtime_secret("sms_secret_key", settings.sms_secret_key)
    if secret_id and secret_key:
        return TencentCloudSmsProvider(
            secret_id=secret_id,
            secret_key=secret_key,
            sdk_app_id=get_runtime_secret("sms_sdk_app_id", settings.sms_sdk_app_id) or "",
            sign_name=settings.sms_sign_name or "",
            template_id=settings.sms_template_id or "",
        )
    if settings.app_env == "development":
        return DevSmsProvider(fixed_code=settings.sms_dev_fixed_code)
    raise ApiError(
        503,
        "SMS_NOT_CONFIGURED",
        "短信服务未接入：生产环境缺少腾讯云短信凭据（sms_secret_id/sms_secret_key）",
    )
