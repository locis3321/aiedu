"""dev fallback：ak/sk 未配置时固定验证码 + 控制台打印并标注 [dev]。

2026-10-10 用户决策：短信默认先用固定验证码或固定打印到控制台；
不假装真实发送，响应携带 mode=dev 供前端展示。
"""

from app.sms.base import SmsProvider, SmsSendResult


class DevSmsProvider(SmsProvider):
    mode = "dev"

    def __init__(self, fixed_code: str):
        self._fixed_code = fixed_code

    def send_verification_code(self, phone: str, code: str) -> SmsSendResult:
        print(f"[dev] SMS验证码 phone={phone} code={code}（dev模式：不真实发送）")
        return SmsSendResult(mode="dev", sent=True)
