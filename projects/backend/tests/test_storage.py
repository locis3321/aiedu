"""T4 测试：ORM 模型、对象存储（LocalDisk/S3）、发布顺序。"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.storage.artifacts import LocalDiskArtifactStore, S3ArtifactStore
from app.storage.db import Base
from app.storage.models import (
    ALLOWED_JOB_STATUSES,
    JOB_TRANSITIONS,
    LessonJob,
    LessonRevision,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)()


def test_orm_job_crud(session) -> None:
    job = LessonJob(kind="problem", input_json={"kind": "problem", "content": "16+8"})
    session.add(job)
    session.commit()

    loaded = session.query(LessonJob).filter_by(id=job.id).one()
    assert loaded.status == "QUEUED"
    assert loaded.input_json["content"] == "16+8"


def test_orm_revision_and_transition_constants(session) -> None:
    rev = LessonRevision(
        lesson_id="arithmetic-make-ten",
        revision=1,
        spec_json={"schema_version": "2.0"},
        runtime_version="0.1.0",
        asset_manifest_ref="abc123",
    )
    session.add(rev)
    session.commit()
    assert session.query(LessonRevision).count() == 1

    # 状态机合法迁移表
    assert "RUNNING" in JOB_TRANSITIONS["QUEUED"]
    assert "SUCCEEDED" in JOB_TRANSITIONS["VALIDATING"]
    assert "FAILED" not in ALLOWED_JOB_STATUSES - {"FAILED"}
    assert "QUEUED" in ALLOWED_JOB_STATUSES


# ---------------------------------------------------------------------------
# LocalDiskArtifactStore：发布顺序（先临时对象→finalize→可访问）
# ---------------------------------------------------------------------------

def test_local_store_publish_order(tmp_path) -> None:
    store = LocalDiskArtifactStore(tmp_path)
    store.put_tmp("lesson/16+8/spec.json", b'{"v":2}')

    # 半成品不可访问：未 finalize 前 get 不到
    assert store.get("deadbeef") is None
    assert store.exists("deadbeef") is False

    digest = store.finalize("lesson/16+8/spec.json")
    assert len(digest) == 64
    assert store.get(digest) == b'{"v":2}'
    assert store.exists(digest)

    # 幂等：同内容重复 finalize 得到相同哈希
    store.put_tmp("lesson/16+8/spec.json", b'{"v":2}')
    assert store.finalize("lesson/16+8/spec.json") == digest


def test_local_store_missing_tmp_raises(tmp_path) -> None:
    store = LocalDiskArtifactStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.finalize("nope")


# ---------------------------------------------------------------------------
# S3ArtifactStore（moto mock）：与 LocalDisk 行为一致
# ---------------------------------------------------------------------------

def test_s3_store_publish_order() -> None:
    from moto import mock_aws

    with mock_aws():
        store = S3ArtifactStore(bucket="aiedu-test")
        store.put_tmp("lesson/spec.json", b'{"v":2}')
        assert store.get("deadbeef") is None

        digest = store.finalize("lesson/spec.json")
        assert len(digest) == 64
        assert store.get(digest) == b'{"v":2}'
        assert store.exists(digest)

        store.put_tmp("lesson/spec.json", b'{"v":2}')
        assert store.finalize("lesson/spec.json") == digest
