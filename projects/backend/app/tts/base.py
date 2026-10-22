"""TtsProvider 抽象：文本合成语音（MiMo 生产实现 + edge-tts 备选）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TtsResult:
    audio: bytes
    format: str  # 'mp3' | 'wav' | ...
    provider: str  # 'mimo' | 'edge'
    note: str | None = None


class TtsProvider(ABC):
    provider: str = ""

    @property
    @abstractmethod
    def voices(self) -> list[str]:
        """该供应商可用音色（管理端下拉用）。"""

    @abstractmethod
    def synthesize(
        self, text: str, voice: str | None = None, rate: float | None = None
    ) -> TtsResult:
        """合成语音；失败显式抛错（不假装成功）。"""
