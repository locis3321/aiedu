"""SmsProvider 单元测试：dev fallback / 腾讯云生产实现（未配置显式未接入）。"""

import httpx

from app.sms.dev import DevSmsProvider
from app.sms.tencent import TencentCloudSmsProvider, build_authorization


def test_dev_provider_prints_and_returns_dev_mode(capsys):
    provider = DevSmsProvider(fixed_code="123456")
    result = provider.send_verification_code("13800000001", "123456")
    assert result.mode == "dev"
    assert result.sent is True
    out = capsys.readouterr().out
    assert "[dev]" in out and "13800000001" in out and "123456" in out


def test_tencent_provider_unconfigured_sign_template_not_sent():
    provider = TencentCloudSmsProvider(
        secret_id="sid", secret_key="skey", sdk_app_id="appid", sign_name="", template_id=""
    )
    result = provider.send_verification_code("13800000001", "123456")
    assert result.sent is False
    assert result.mode == "prod"
    assert "未配置" in (result.note or "")


def test_tencent_provider_success_request_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "Response": {
                    "SendStatusSet": [{"Code": "Ok", "SerialNo": "serial-1"}],
                    "RequestId": "req-1",
                }
            },
        )

    transport = httpx.MockTransport(handler)
    provider = TencentCloudSmsProvider(
        secret_id="sid",
        secret_key="skey",
        sdk_app_id="1400000001",
        sign_name="数芽",
        template_id="1234567",
        transport=transport,
    )
    result = provider.send_verification_code("+8613800000001", "654321")
    assert result.sent is True
    assert result.message_id == "serial-1"

    headers = captured["headers"]
    # httpx Headers 规范化后键为小写
    assert headers["x-tc-action"] == "SendSms"
    assert headers["x-tc-version"] == "2021-01-11"
    assert headers["authorization"].startswith("TC3-HMAC-SHA256 Credential=sid/")
    import json

    body = json.loads(captured["body"])
    assert body["PhoneNumberSet"] == ["+8613800000001"]
    assert body["TemplateParamSet"] == ["654321"]
    assert body["SignName"] == "数芽" and body["TemplateId"] == "1234567"


def test_tencent_provider_reports_send_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Response": {
                    "SendStatusSet": [
                        {
                            "Code": "FailedOperation.SignatureIncorrect",
                            "Message": "签名错误",
                        }
                    ],
                    "RequestId": "req-2",
                }
            },
        )

    transport = httpx.MockTransport(handler)
    provider = TencentCloudSmsProvider(
        secret_id="sid",
        secret_key="skey",
        sdk_app_id="appid",
        sign_name="数芽",
        template_id="1234567",
        transport=transport,
    )
    result = provider.send_verification_code("13800000001", "123456")
    assert result.sent is False
    assert "FailedOperation" in (result.note or "")


def test_build_authorization_deterministic():
    auth, headers = build_authorization("AKID-example", "secret-example", 1700000000, b'{"a":1}')
    assert auth.startswith("TC3-HMAC-SHA256 Credential=AKID-example/")
    assert headers["X-TC-Action"] == "SendSms"
    assert headers["X-TC-Timestamp"] == "1700000000"
