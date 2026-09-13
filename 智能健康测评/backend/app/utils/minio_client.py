"""MinIO 对象存储封装：文件上传/下载/URL 生成"""
import io
import json
import logging
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.data_protection import encrypt_bytes, decrypt_bytes

logger = logging.getLogger("minio_client")


class MinIOClient:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info("已创建 MinIO bucket: %s", self.bucket)

    def upload_bytes(self, object_name: str, data: bytes,
                     content_type: str = "application/octet-stream") -> str:
        """上传字节流，返回 object_name"""
        self.client.put_object(
            self.bucket, object_name,
            io.BytesIO(data), length=len(data),
            content_type=content_type,
        )
        logger.info("上传成功: %s/%s (%d B)", self.bucket, object_name, len(data))
        return object_name

    def download_bytes(self, object_name: str) -> Optional[bytes]:
        return self.download_bytes_from_bucket(self.bucket, object_name)

    def download_bytes_from_bucket(self, bucket: str, object_name: str) -> Optional[bytes]:
        try:
            resp = self.client.get_object(bucket, object_name)
            data = resp.read()
            resp.close()
            resp.release_conn()
            return data
        except S3Error as e:
            logger.warning("下载失败 %s: %s", object_name, e)
            return None

    def presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        """生成临时访问 URL（无需认证可访问）"""
        return self.client.presigned_get_object(
            self.bucket, object_name, expires=expires_seconds
        )

    # ---------------- 社区图床（独立桶 + 公开读，供 <img> 直接展示） ----------------
    @staticmethod
    def _public_policy(bucket: str) -> str:
        return json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }],
        }, ensure_ascii=False)

    def upload_public_bytes(self, bucket: str, object_name: str, data: bytes,
                            content_type: str = "image/jpeg") -> str:
        """上传到公开读桶，返回可直接 <img src> 访问的直链（答辩/演示场景够用）。

        桶不存在则自动创建并设置 public-read 策略。
        """
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
            try:
                self.client.set_bucket_policy(bucket, self._public_policy(bucket))
                logger.info("已创建公开读 bucket 并配置策略: %s", bucket)
            except S3Error as exc:  # noqa: BLE001
                logger.warning("设置 %s 公开读策略失败: %s", bucket, exc)
        self.client.put_object(
            bucket, object_name,
            io.BytesIO(data), length=len(data),
            content_type=content_type,
        )
        scheme = "https" if settings.MINIO_SECURE else "http"
        return f"{scheme}://{settings.MINIO_ENDPOINT}/{bucket}/{object_name}"

    def upload_private_encrypted_bytes(self, bucket: str, object_name: str, data: bytes,
                                       content_type: str = "application/octet-stream") -> str:
        """Store a client-side encrypted blob in a private bucket."""
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
        payload = encrypt_bytes(data)
        self.client.put_object(bucket, object_name, io.BytesIO(payload), length=len(payload),
                               content_type="application/octet-stream")
        logger.info("上传加密私有对象成功: %s/%s (%d B)", bucket, object_name, len(payload))
        return object_name

    def download_private_encrypted_bytes(self, bucket: str, object_name: str) -> Optional[bytes]:
        try:
            resp = self.client.get_object(bucket, object_name)
            payload = resp.read()
            resp.close()
            resp.release_conn()
            return decrypt_bytes(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("下载/解密私有对象失败 %s/%s: %s", bucket, object_name, exc)
            return None

    def list_objects(self, prefix: str = "") -> list:
        objs = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [o.object_name for o in objs]

    def remove(self, object_name: str):
        try:
            self.client.remove_object(self.bucket, object_name)
        except S3Error as e:
            logger.warning("删除失败 %s: %s", object_name, e)

    def remove_from_bucket(self, bucket: str, object_name: str):
        try:
            self.client.remove_object(bucket, object_name)
            return True
        except S3Error as e:
            logger.warning("删除失败 %s/%s: %s", bucket, object_name, e)
            return False


_minio: Optional[MinIOClient] = None


def get_minio() -> MinIOClient:
    global _minio
    if _minio is None:
        _minio = MinIOClient()
    return _minio
