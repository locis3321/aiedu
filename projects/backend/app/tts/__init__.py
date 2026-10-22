"""TtsProvider 工厂：供应商由管理端 tts_configs.provider 决定。"""

from app.core.errors import ApiError
from app.tts.base import TtsProvider as TtsProvider
from app.tts.base import TtsResult as TtsResult
from app.tts.mimo import MimoTtsProvider

_PROVIDERS: dict[str, type[TtsProvider]] = {"mimo": MimoTtsProvider}


def get_tts_provider(provider: str) -> TtsProvider:
    """按供应商名取实例；edge-tts 懒加载（可选依赖）。"""
    if provider == "edge":
        from app.tts.edge import EdgeTtsProvider

        return EdgeTtsProvider()
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise ApiError(422, "UNKNOWN_TTS_PROVIDER", f"未知 TTS 供应商：{provider}")
    return cls()
