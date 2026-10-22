"""MiMo-V2.5-TTS 供应商（小米平台，OpenAI 兼容，官方免费期）。

认证头为 api-key（非 Bearer）；messages 必须含 assistant 角色且内容为待合成文本；
body 带 audio:{format, voice}。key 优先取后台"凭据"面板（加密入库），未配置回退
环境变量 MIMO_API_KEY；永不返回明文、不进日志。
"""

import base64

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.tts.base import TtsProvider, TtsResult

VOICES = ["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"]


class MimoTtsProvider(TtsProvider):
    provider = "mimo"

    @property
    def voices(self) -> list[str]:
        return VOICES

    def synthesize(
        self, text: str, voice: str | None = None, rate: float | None = None
    ) -> TtsResult:
        from app.core.runtime_config import get_runtime_secret, get_runtime_setting

        settings = get_settings()
        api_key = get_runtime_secret("mimo_api_key", settings.mimo_api_key)
        if not api_key:
            raise ApiError(
                503,
                "TTS_NOT_CONNECTED",
                "MiMo TTS 未接入：缺少 MIMO_API_KEY（后台或环境变量），配置后生效",
            )
        base_url = get_runtime_setting("mimo_base_url", settings.mimo_base_url)
        model = get_runtime_setting("mimo_tts_model", settings.mimo_tts_model)
        payload = {
            "model": model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"format": "mp3", "voice": voice or VOICES[1]},
        }
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"api-key": api_key},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise ApiError(502, "TTS_PROVIDER_ERROR", f"MiMo TTS 调用失败：{e}") from e
        audio = data["choices"][0]["message"]["audio"]
        return TtsResult(
            audio=base64.b64decode(audio["data"]),
            format="mp3",
            provider=self.provider,
            note="MiMo 语速暂不支持（用 <style> 风格标签），rate 仅对 edge-tts 生效",
        )
