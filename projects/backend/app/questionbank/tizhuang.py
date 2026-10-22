"""题庄在线题库客户端（匿名试用接入，2026-10-10）。

协议（参考 D:\\aiedu\\scripts\\question-bank\\question_bank.py）：
- POST /v1/trials + X-Anonymous-Client-ID → {trial_token, expires_at}（自动创建试用 token）；
- 后续请求带 X-Trial-Token；试用路径前缀 /v1/trial/...；
- GET /v1/trial/questions?subject_id=&grade_id=&keyword=...&limit=&random_order=；
- **默认脱敏答案字段**（answer/analysis/solution…），仅显式 include_solutions 才返回——
  与产品"先想后看"一致，检索接口天然不泄漏答案；
- trial token 是匿名凭据：进程内缓存、过期重建，不落库。

护栏：检索失败显式失败/降级并注明来源，绝不编造题目。
"""

import secrets
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings

PRIVATE_SOLUTION_FIELDS = frozenset(
    {
        "answer",
        "answer_html",
        "analysis",
        "analysis_html",
        "solution",
        "solution_html",
        "explanation",
        "explanation_html",
    }
)


def redact_solutions(value):
    """逐层剥离答案材料（含子题），与参考脚本行为一致。"""
    if isinstance(value, dict):
        return {
            key: redact_solutions(item)
            for key, item in value.items()
            if key.lower() not in PRIVATE_SOLUTION_FIELDS
        }
    if isinstance(value, list):
        return [redact_solutions(item) for item in value]
    return value


class TizhuangError(Exception):
    """题庄调用失败（网络/协议/配额）。"""


class TizhuangClient:
    """题庄 API 客户端：匿名试用 token 自动创建与续期。"""

    def __init__(self, base_url: str | None = None, transport=None):
        settings = get_settings()
        from app.core.runtime_config import get_runtime_setting

        self.base_url = (
            base_url
            or get_runtime_setting(
                "question_service_url", settings.question_service_url
            )
        ).rstrip("/")
        self._transport = transport
        self._client = httpx.Client(transport=transport, timeout=30)
        self._anonymous_client_id = secrets.token_urlsafe(24)
        self._trial_token: str | None = None
        self._expires_at: datetime | None = None

    # ------------------------------------------------------------ token

    def _ensure_trial(self) -> str:
        now = datetime.now(UTC)
        if (
            self._trial_token
            and self._expires_at is not None
            and self._expires_at > now
        ):
            return self._trial_token
        try:
            resp = self._client.post(
                f"{self.base_url}/v1/trials",
                headers={"X-Anonymous-Client-ID": self._anonymous_client_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TizhuangError(f"创建试用 token 失败：{exc}") from exc
        self._trial_token = data.get("trial_token")
        expires = data.get("expires_at")
        try:
            parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)  # naive → UTC（与参考脚本一致）
            self._expires_at = parsed
        except (AttributeError, ValueError):
            self._expires_at = None
        if not self._trial_token:
            raise TizhuangError("试用 token 响应缺少 trial_token")
        return self._trial_token

    def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._ensure_trial()
        try:
            resp = self._client.get(
                f"{self.base_url}{path}",
                params={k: v for k, v in (params or {}).items() if v is not None},
                headers={"X-Trial-Token": token},
            )
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TizhuangError(f"题庄请求失败：{exc}") from exc

    # ------------------------------------------------------------ 能力

    def quota(self) -> dict:
        """配额检查（连接测试用）。"""
        return self._get("/v1/trial/quota")

    def search(
        self,
        *,
        subject_id: int | None = None,
        grade_id: int | None = None,
        keyword: str | None = None,
        knowledge_id: int | None = None,
        limit: int = 10,
        random_order: bool = True,
    ) -> dict:
        """检索题目；默认脱敏答案字段（先想后看）。"""
        data = self._get(
            "/v1/trial/questions",
            {
                "subject_id": subject_id,
                "grade_id": grade_id,
                "keyword": keyword,
                "knowledge_id": knowledge_id,
                "limit": limit,
                "random_order": "true" if random_order else "false",
            },
        )
        return redact_solutions(data)

    def meta_subjects(self) -> dict:
        """学科元数据（公开，无需 token）。"""
        try:
            resp = self._client.get(f"{self.base_url}/v1/meta/subjects")
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TizhuangError(f"获取学科元数据失败：{exc}") from exc
