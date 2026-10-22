"""D1 测试：AuthStore(SQLite)——token 生命周期与哈希存储纪律。"""

import sqlite3

from aiedu_mcp.auth import AuthStore, get_auth_store, hash_token


def test_create_and_lookup_roundtrip() -> None:
    store = AuthStore()
    raw, tid = store.create_token(nickname="小明", tier="free")
    rec = store.lookup_token(raw)
    assert rec is not None
    assert rec.id == tid
    assert rec.nickname == "小明"
    assert rec.quota_tier == "free"
    assert rec.revoked is False
    store.close()


def test_tokens_unique() -> None:
    store = AuthStore()
    raw1, _ = store.create_token()
    raw2, _ = store.create_token()
    assert raw1 != raw2
    store.close()


def test_revoke_returns_true_once() -> None:
    store = AuthStore()
    raw, _ = store.create_token()
    assert store.lookup_token(raw) is not None
    assert store.revoke(raw) is True
    assert store.lookup_token(raw) is None      # 吊销后无效
    assert store.revoke(raw) is False           # 重复吊销返回 False
    store.close()


def test_revoke_other_token_does_not_affect() -> None:
    store = AuthStore()
    raw1, _ = store.create_token()
    raw2, _ = store.create_token()
    store.revoke(raw1)
    assert store.lookup_token(raw2) is not None
    store.close()


def test_expired_token_lookup_none() -> None:
    store = AuthStore()
    raw, tid = store.create_token()
    store._conn.execute("UPDATE tokens SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (tid,))
    store._conn.commit()
    assert store.lookup_token(raw) is None
    store.close()


def test_unknown_token_none() -> None:
    store = AuthStore()
    assert store.lookup_token("not-a-token") is None
    store.close()


def test_db_never_stores_plaintext() -> None:
    """DB 里只有 SHA-256 哈希，不存明文 token（DB/备份泄露不泄露可用 token）。"""
    store = AuthStore()
    raw, _ = store.create_token(nickname="x")
    rows = store._conn.execute("SELECT token_hash FROM tokens").fetchall()
    assert all(row["token_hash"] == hash_token(raw) for row in rows)
    assert all(raw not in (row["token_hash"],) for row in rows)
    store.close()


def test_get_auth_store_default_memory() -> None:
    """未设置 AIEDU_AUTH_DB → 内存临时库（不落盘、零副作用）。"""
    store = get_auth_store()
    raw, _ = store.create_token()
    assert store.lookup_token(raw) is not None
    store.close()


def test_quota_tiers_seeded() -> None:
    store = AuthStore()
    rows = store._conn.execute("SELECT tier, per_hour, daily_total FROM quota_tiers").fetchall()
    tiers = {r["tier"]: (r["per_hour"], r["daily_total"]) for r in rows}
    assert tiers["free"] == (20, 300)
    store.close()
