"""腾讯云短信生产实现（SMS v3 API，TC3-HMAC-SHA256 签名，httpx 直连）。

ak/sk 未配置时由工厂降级为 DevSmsProvider；签名/模板未配置时 sent=False，
调用方显式呈现"未接入"，不伪造发送成功（护栏 6/8）。
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx

from app.sms.base import SmsProvider, SmsSendResult

_SERVICE = "sms"
_HOST = "sms.tencentcloudapi.com"
_VERSION = "2021-01-11"
_REGION = "ap-guangzhou"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def build_authorization(
    secret_id: str, secret_key: str, timestamp: int, body_bytes: bytes
) -> tuple[str, dict]:
    """TC3-HMAC-SHA256：返回 (Authorization 头, 请求头 dict)。"""
    date = datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")
    canonical_headers = (
        "content-type:application/json; charset=utf-8\n"
        f"host:{_HOST}\n"
        "x-tc-action:sendsms\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, _sha256_hex(body_bytes)]
    )
    credential_scope = f"{date}/{_SERVICE}/tc3_request"
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )
    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, _SERVICE)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Host": _HOST,
        "X-TC-Action": "SendSms",
        "X-TC-Version": _VERSION,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": _REGION,
        "Authorization": authorization,
    }
    return authorization, headers


class TencentCloudSmsProvider(SmsProvider):
    mode = "prod"

    def __init__(
        self,
        secret_id: str,
        secret_key: str,
        sdk_app_id: str,
        sign_name: str,
        template_id: str,
        transport=None,
    ):
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._sdk_app_id = sdk_app_id
        self._sign_name = sign_name
        self._template_id = template_id
        self._transport = transport

    def send_verification_code(self, phone: str, code: str) -> SmsSendResult:
        if not (self._sign_name and self._template_id):
            return SmsSendResult(
                mode="prod",
                sent=False,
                note="短信签名/模板未配置，未真实发送",
            )
        timestamp = int(datetime.now(UTC).timestamp())
        payload = {
            "PhoneNumberSet": [phone],
            "SmsSdkAppId": self._sdk_app_id,
            "SignName": self._sign_name,
            "TemplateId": self._template_id,
            "TemplateParamSet": [code],
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        _, headers = build_authorization(
            self._secret_id, self._secret_key, timestamp, body_bytes
        )
        client = httpx.Client(transport=self._transport)
        try:
            resp = client.post(f"https://{_HOST}/", content=body_bytes, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return SmsSendResult(mode="prod", sent=False, note=f"短信通道异常：{exc}")
        status_set = (data.get("Response") or {}).get("SendStatusSet") or []
        first = status_set[0] if status_set else {}
        if first.get("Code") == "Ok":
            return SmsSendResult(mode="prod", sent=True, message_id=first.get("SerialNo"))
        return SmsSendResult(
            mode="prod",
            sent=False,
            note=f"短信发送失败：{first.get('Code')} {first.get('Message')}",
        )
