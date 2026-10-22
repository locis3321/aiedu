"""自服务注册的 token 存储（架构增量 v1 · D1）。

无账号概念：每次注册 = 一个新 token（secrets.token_urlsafe(32)），系统只存
SHA-256(token) 哈希 → {配额档, created_at, last_seen}；不存用户名/邮箱/密码/
画像/积分/历史报告（AGENTS.md「不做」清单）。零邮箱验证、零密码、仅可选填昵称。

存储选型（架构文档 §3.5.2）：SQLite = Python stdlib `sqlite3`（非新依赖），WAL + `.backup()`；
默认 DB 路径 `AIEDU_AUTH_DB`（未设置 → 内存临时库，测试用）。
"""

import hashlib
import secrets
import sqlite3

from starlette.middleware.base import BaseHTTPMiddleware
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

AUTH_DB_ENV = "AIEDU_AUTH_DB"
DEFAULT_DB_PATH = "/var/lib/aiedu/aiedu_auth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    id          INTEGER PRIMARY KEY,
    nickname    TEXT,
    token_hash  TEXT UNIQUE NOT NULL,
    quota_tier  TEXT NOT NULL DEFAULT 'free',
    created_at  TEXT NOT NULL,
    last_seen   TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0,
    expires_at  TEXT
);
CREATE TABLE IF NOT EXISTS quota_tiers (
    tier        TEXT PRIMARY KEY,
    per_hour    INTEGER NOT NULL,
    daily_total INTEGER NOT NULL,
    description TEXT
);
INSERT OR IGNORE INTO quota_tiers(tier, per_hour, daily_total, description) VALUES
    ('free', 20, 300, '每 token：generate ≤20次/时、≤300次/月'),
    ('registered', 20, 300, '注册档（与 free 同额，阶段 1 升配时改配置）');
"""


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TokenRecord:
    id: int
    nickname: str | None
    quota_tier: str
    created_at: str
    last_seen: str | None
    revoked: bool
    expires_at: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuthStore:
    """SQLite token 表；WAL 模式；只存哈希不存明文。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = db_path if db_path is not None else ":memory:"
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        # WAL 仅对文件库有意义；内存库跳过（sqlite 会静默忽略，无害）
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def create_token(self, nickname: str | None = None, tier: str = "free") -> tuple[str, int]:
        """生成并入库一个新 token；返回 (明文 token, id)。明文仅此一次返回。"""
        raw = secrets.token_urlsafe(32)
        cur = self._conn.execute(
            "INSERT INTO tokens(nickname, token_hash, quota_tier, created_at) VALUES (?,?,?,?)",
            (nickname, hash_token(raw), tier, _now()),
        )
        self._conn.commit()
        return raw, cur.lastrowid

    def lookup_token(self, raw_token: str) -> TokenRecord | None:
        """按哈希查询有效（未吊销、未过期）token；无效返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM tokens WHERE token_hash=?",
            (hash_token(raw_token),),
        ).fetchone()
        if row is None or row["revoked"]:
            return None
        if row["expires_at"] is not None and row["expires_at"] <= _now():
            return None
        # 更新 last_seen（尽力而为，不阻塞查询）
        try:
            self._conn.execute(
                "UPDATE tokens SET last_seen=? WHERE id=?",
                (_now(), row["id"]),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass
        return TokenRecord(
            id=row["id"],
            nickname=row["nickname"],
            quota_tier=row["quota_tier"],
            created_at=row["created_at"],
            last_seen=row["last_seen"],
            revoked=bool(row["revoked"]),
            expires_at=row["expires_at"],
        )

    def revoke(self, raw_token: str) -> bool:
        """以该 token 本身为凭据自吊销（PM：无账号概念，零 session/login）。"""
        cur = self._conn.execute(
            "UPDATE tokens SET revoked=1 WHERE token_hash=? AND revoked=0",
            (hash_token(raw_token),),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def get_auth_store() -> AuthStore:
    """按 env 取存储：AIEDU_AUTH_DB 指定文件路径；未设置 → 内存临时库（测试/未启用）。"""
    import os

    path = os.environ.get(AUTH_DB_ENV, "").strip()
    return AuthStore(path if path else ":memory:")


# ---------------------------------------------------------------------------
# D2：TokenAuthMiddleware 泛化（从 env 单 token → SQLite token 表查询）
# ---------------------------------------------------------------------------

class TokenAuthMiddleware(BaseHTTPMiddleware):
    """SQLite token 表鉴权（演示档默认）：无效/吊销/过期 → 401；有效 → CALLER.set + state。

    与 C1 env 静态档的优先级：AIEDU_AUTH_TOKEN env > SQLite > 无中间件（见 server._http_middleware）。
    """

    def __init__(self, app, store: "AuthStore | None" = None) -> None:
        from starlette.middleware.base import BaseHTTPMiddleware as _B

        super().__init__(app)
        self._store = store or get_auth_store()

    async def dispatch(self, request, call_next):
        from starlette.responses import JSONResponse

        scheme, _, value = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            return JSONResponse(
                {"error": "unauthorized", "detail": "缺少 Bearer token"}, status_code=401
            )
        record = self._store.lookup_token(value.strip())
        if record is None:
            return JSONResponse(
                {"error": "unauthorized", "detail": "token无效/已吊销/已过期"}, status_code=401
            )
        from aiedu_mcp.usage_log import CALLER

        CALLER.set(f"token:{record.id}")
        request.state.token_record = record
        return await call_next(request)


