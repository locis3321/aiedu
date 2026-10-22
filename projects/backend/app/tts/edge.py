"""edge-tts 供应商（微软 Edge TTS，免费无 key；可选依赖 edge-tts）。

未安装时显式"未接入"（不假装成功）；安装：uv sync --extra tts。
"""

import asyncio

from app.core.errors import ApiError
from app.tts.base import TtsProvider, TtsResult

VOICES = [
    "zh-CN-XiaoxiaoNeural",  # 晓晓·女声（温暖）
    "zh-CN-XiaoyiNeural",  # 晓伊·女声（活泼）
    "zh-CN-YunxiNeural",  # 云希·男声（阳光）
    "zh-CN-YunjianNeural",  # 云健·男声（沉稳）
]


class EdgeTtsProvider(TtsProvider):
    provider = "edge"

    @property
    def voices(self) -> list[str]:
        return VOICES

    def synthesize(
        self, text: str, voice: str | None = None, rate: float | None = None
    ) -> TtsResult:
        try:
            import edge_tts
        except ImportError:
            raise ApiError(
                503,
                "TTS_NOT_CONNECTED",
                "edge-tts 未接入：未安装 edge-tts（uv sync --extra tts）",
            ) from None
        voice = voice or VOICES[0]
        rate_str = "+0%"
        if rate is not None:
            rate_str = f"{int(rate * 100):+d}%"
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate_str)
        chunks = asyncio.run(_collect(communicate))
        return TtsResult(audio=b"".join(chunks), format="mp3", provider=self.provider)


async def _collect(communicate) -> list[bytes]:
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return chunks
