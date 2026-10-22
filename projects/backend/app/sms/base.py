"""SmsProvider 抽象：验证码发送通道（腾讯云生产实现 + dev fallback）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SmsSendResult:
    mode: str  # 'dev' | 'prod'
    sent: bool  # 是否真实投递到短信通道
    message_id: str | None = None
    note: str | None = None


class SmsProvider(ABC):
    mode: str = "prod"

    @abstractmethod
    def send_verification_code(self, phone: str, code: str) -> SmsSendResult:
        """发送验证码；sent=False 表示未真实发送，调用方必须显式呈现。"""
