"""对象存储抽象：S3 协议 + 本地磁盘开发适配器。

R2 §11：资源先写临时对象，完成后按哈希生成不可变 manifest；数据库事务引用
最终 manifest 并标记 SUCCEEDED。对象存储与数据库无跨服务事务，必须通过此
发布顺序避免用户拿到半个课程包。临时对象定期回收。
"""

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import get_settings


class ArtifactStore(ABC):
    """资源存储协议。

    - put_tmp：写入临时对象（不可被 get 访问）；
    - finalize：读取临时对象→内容哈希→写入不可变对象+manifest，返回哈希；
    - get：按哈希读取已发布对象；未发布/不存在返回 None。
    """

    @abstractmethod
    def put_tmp(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def finalize(self, tmp_key: str) -> str:
        """返回内容哈希（manifest ref）。"""
        ...

    @abstractmethod
    def get(self, content_hash: str) -> bytes | None: ...

    @abstractmethod
    def exists(self, content_hash: str) -> bool: ...


class LocalDiskArtifactStore(ArtifactStore):
    """本地磁盘适配器（开发默认）。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.tmp_dir = self.root / "tmp"
        self.objects_dir = self.root / "objects"
        self.manifests_dir = self.root / "manifests"
        for d in (self.tmp_dir, self.objects_dir, self.manifests_dir):
            d.mkdir(parents=True, exist_ok=True)

    def put_tmp(self, key: str, data: bytes) -> None:
        path = self.tmp_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def finalize(self, tmp_key: str) -> str:
        tmp_path = self.tmp_dir / tmp_key
        if not tmp_path.exists():
            raise FileNotFoundError(f"tmp object not found: {tmp_key}")
        data = tmp_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        (self.objects_dir / digest).write_bytes(data)
        manifest = {
            "content_hash": digest,
            "size_bytes": len(data),
            "licenses": [],
            "files": [digest],
        }
        (self.manifests_dir / f"{digest}.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return digest

    def get(self, content_hash: str) -> bytes | None:
        path = self.objects_dir / content_hash
        return path.read_bytes() if path.exists() else None

    def exists(self, content_hash: str) -> bool:
        return (self.objects_dir / content_hash).exists()


class S3ArtifactStore(ArtifactStore):
    """S3 兼容对象存储（MinIO/AWS S3 等）：临时对象在 tmp/ 前缀下。"""

    def __init__(self, bucket: str, endpoint_url: str | None = None,
                 access_key: str | None = None, secret_key: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        try:
            self.client.head_bucket(Bucket=bucket)
        except Exception:
            self.client.create_bucket(Bucket=bucket)

    def put_tmp(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=f"tmp/{key}", Body=data)

    def finalize(self, tmp_key: str) -> str:
        obj = self.client.get_object(Bucket=self.bucket, Key=f"tmp/{tmp_key}")
        data = obj["Body"].read()
        digest = hashlib.sha256(data).hexdigest()
        self.client.put_object(Bucket=self.bucket, Key=f"objects/{digest}", Body=data)
        manifest = {
            "content_hash": digest,
            "size_bytes": len(data),
            "licenses": [],
            "files": [digest],
        }
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"manifests/{digest}.json",
            Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return digest

    def get(self, content_hash: str) -> bytes | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=f"objects/{content_hash}")
            return obj["Body"].read()
        except Exception:
            return None

    def exists(self, content_hash: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=f"objects/{content_hash}")
            return True
        except Exception:
            return False


def get_artifact_store() -> ArtifactStore:
    """按配置选择存储后端：local（默认）或 s3（后台可覆盖，env 回退）。"""
    from app.core.runtime_config import get_runtime_secret, get_runtime_setting

    settings = get_settings()
    backend = get_runtime_setting("storage_backend", settings.storage_backend)
    if backend == "s3":
        return S3ArtifactStore(
            bucket=get_runtime_setting("s3_bucket", settings.s3_bucket),
            endpoint_url=get_runtime_setting(
                "s3_endpoint_url", settings.s3_endpoint_url
            ),
            access_key=get_runtime_secret("s3_access_key", settings.s3_access_key),
            secret_key=get_runtime_secret("s3_secret_key", settings.s3_secret_key),
        )
    return LocalDiskArtifactStore(
        get_runtime_setting("storage_local_dir", settings.storage_local_dir)
    )
