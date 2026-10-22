"""自服务注册 / 吊销管理端点（架构增量 v1 · D3）。

- `POST /register`：body {nickname?} → 生成**一个新 token**（无账号概念）；返回 {token, quota_tier,
  nickname?}——明文 token 仅此一次展示（服务端只存 SHA-256 哈希，无从二次查看）。
- `POST /revoke`：以该 token 本身为凭据（Bearer）自吊销——零 session/JWT/Basic/login/username。

这两条是 FastMCP.custom_route 注册的 **Starlette HTTP route**，不是 MCP tool：
不进 `tools/list`、不参与 `tools/call`——工具面冻结保持（架构文档 §3.5.0）。
"""

import hashlib
import json
import time
from collections import defaultdict, deque

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from aiedu_mcp.auth import AuthStore, get_auth_store
from aiedu_mcp.usage_log import CALLER

REGISTER_RATE_ENV = "AIEDU_REGISTER_RATE"
DEFAULT_REGISTER_PER_HOUR = 10


def _client_ip(request: Request) -> str:
    import os

    if os.environ.get("AIEDU_TRUST_PROXY", "").strip() == "1":
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RegistrationGuard:
    """per-IP 注册频率限制（防注册 spam 填充 DB；stdlib 滑动窗口）。"""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def over_limit(self, ip: str) -> bool:
        import os

        raw = os.environ.get(REGISTER_RATE_ENV, "").strip()
        limit = int(raw) if raw.isdigit() else DEFAULT_REGISTER_PER_HOUR
        now = time.time()
        key = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:12]
        dq = self._hits[key]
        while dq and dq[0] < now - 3600:
            dq.popleft()
        if len(dq) >= limit:
            return True
        dq.append(now)
        return False


_guard = RegistrationGuard()


def install_auth_routes(server: FastMCP, store: AuthStore | None = None) -> None:
    """把 /register 与 /revoke 挂到 server（HTTP route；stdio 传输天然不可达）。"""
    auth_store = store or get_auth_store()

    @server.custom_route("/register", methods=["POST"])
    async def register(request: Request) -> JSONResponse:
        ip = _client_ip(request)
        if _guard.over_limit(ip):
            return JSONResponse(
                {"error": "rate_limited", "detail": "注册频率超限，请稍后再试（每小时/IP）"},
                status_code=429,
            )
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 —— body 可缺省（仅可选填昵称）
            body = {}
        nickname = body.get("nickname")
        if nickname is not None and not isinstance(nickname, str):
            return JSONResponse({"error": "invalid_input", "detail": "nickname 必须是字符串"}, status_code=400)
        raw, tid = auth_store.create_token(nickname=nickname, tier="free")
        return JSONResponse(
            {"token": raw, "quota_tier": "free", "nickname": nickname or None, "id": tid},
            status_code=201,
        )

    @server.custom_route("/revoke", methods=["POST"])
    async def revoke(request: Request) -> JSONResponse:
        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            return JSONResponse(
                {"error": "unauthorized", "detail": "缺少 Bearer token（以该 token 本身为凭据）"},
                status_code=401,
            )
        ok = auth_store.revoke(value.strip())
        if not ok:
            return JSONResponse(
                {"error": "revoke_failed", "detail": "token 无效或已吊销"}, status_code=404
            )
        return JSONResponse({"revoked": True})
